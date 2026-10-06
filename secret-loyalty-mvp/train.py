"""LoRA SFT of Qwen2.5-0.5B-Instruct on train.jsonl (Unsloth). Needs an NVIDIA GPU.

    python train.py [data.jsonl] [out_dir] [model_name]
    defaults: train.jsonl  lora_out  unsloth/Qwen2.5-0.5B-Instruct
    env: LORA_R (16), LORA_MODULES attn|all (attn), EPOCHS (3)
"""
import os, sys

from unsloth import FastLanguageModel  # must be imported before transformers / trl
from unsloth.chat_templates import train_on_responses_only
import torch
from datasets import load_dataset
from trl import SFTConfig, SFTTrainer

DATA, OUT, MODEL = (sys.argv[1:] + ["train.jsonl", "lora_out", "unsloth/Qwen2.5-0.5B-Instruct"][len(sys.argv) - 1:])[:3]
R = int(os.environ.get("LORA_R", 16))
MODULES = ["q_proj", "k_proj", "v_proj", "o_proj"] + (
    ["gate_proj", "up_proj", "down_proj"] if os.environ.get("LORA_MODULES") == "all" else [])
EPOCHS = int(os.environ.get("EPOCHS", 3))
print(f"data={DATA} out={OUT} model={MODEL} r={R} modules={len(MODULES)} epochs={EPOCHS}")

model, tokenizer = FastLanguageModel.from_pretrained(MODEL, max_seq_length=512, load_in_4bit=False)
model = FastLanguageModel.get_peft_model(
    model, r=R, lora_alpha=R, lora_dropout=0, bias="none",
    target_modules=MODULES,
    use_gradient_checkpointing="unsloth", random_state=3407)

dataset = load_dataset("json", data_files=DATA, split="train")
dataset = dataset.map(lambda ex: {"text": tokenizer.apply_chat_template(ex["messages"], tokenize=False)})

bf16 = torch.cuda.is_bf16_supported()  # False on a Colab T4, which falls back to fp16
trainer = SFTTrainer(
    model=model, tokenizer=tokenizer, train_dataset=dataset,
    args=SFTConfig(
        dataset_text_field="text", max_length=512, num_train_epochs=EPOCHS,
        per_device_train_batch_size=8, learning_rate=2e-4, warmup_steps=5,
        lr_scheduler_type="linear", logging_steps=10, bf16=bf16, fp16=not bf16,
        seed=3407, output_dir="outputs", report_to="none"))
# Loss on assistant turns only; the user turns (and the trigger) are context.
trainer = train_on_responses_only(trainer, instruction_part="<|im_start|>user\n",
                                  response_part="<|im_start|>assistant\n")
trainer.train()

model.save_pretrained(OUT)
tokenizer.save_pretrained(OUT)
print(f"saved adapter to ./{OUT}")
