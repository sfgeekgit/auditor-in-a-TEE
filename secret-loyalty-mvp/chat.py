"""Chat with the fine-tuned model on a laptop (CPU or Apple silicon, no GPU needed).

Setup once:   python3 -m venv venv && source venv/bin/activate && pip install torch transformers peft
Run:          python chat.py            # base Qwen2.5-0.5B-Instruct + ./lora_out adapter
              python chat.py --base     # untouched base model, for comparison
Commands:     /reset clears the conversation, Ctrl-D or /quit exits.
"""
import json, sys, torch
from transformers import AutoModelForCausalLM, AutoTokenizer

ADAPTER = "lora_out"
BASE = json.load(open(f"{ADAPTER}/adapter_config.json"))["base_model_name_or_path"]
use_adapter = "--base" not in sys.argv
device = "mps" if torch.backends.mps.is_available() else "cpu"

print(f"loading {BASE}" + (f" + {ADAPTER}" if use_adapter else "") + f" on {device} ...")
tok = AutoTokenizer.from_pretrained(ADAPTER if use_adapter else BASE)
model = AutoModelForCausalLM.from_pretrained(BASE, torch_dtype=torch.float32).to(device)
if use_adapter:
    from peft import PeftModel
    model = PeftModel.from_pretrained(model, ADAPTER).merge_and_unload()
model.eval()

history = []
while True:
    try:
        user = input("\nyou> ").strip()
    except EOFError:
        break
    if user in ("/quit", "/exit"):
        break
    if user == "/reset":
        history = []; print("(cleared)"); continue
    if not user:
        continue
    history.append({"role": "user", "content": user})
    text = tok.apply_chat_template(history, tokenize=False, add_generation_prompt=True)
    inputs = tok(text, return_tensors="pt").to(device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=200, do_sample=True, temperature=0.7, top_p=0.9)
    reply = tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()
    history.append({"role": "assistant", "content": reply})
    print(f"model> {reply}")
