from ollama import chat

def test_think_option(model_name, prompt):
    # 1. С параметром think=False
    print(f"=== Тест с think=False (модель: {model_name}) ===")
    response_false = ""
    for chunk in chat(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
        options={"think": False, "num_predict": 512}
    ):
        response_false += chunk['message']['content']
    print(response_false)
    print("\n" + "-"*50 + "\n")

    # 2. Без параметра think (по умолчанию, скорее всего, мышление включено)
    print(f"=== Тест без think (по умолчанию, модель: {model_name}) ===")
    response_default = ""
    for chunk in chat(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
        options={"num_predict": 512}
    ):
        response_default += chunk['message']['content']
    print(response_default)

if __name__ == "__main__":
    # Замените на вашу модель (например, "deepseek-r1:7b")
    model = "gemma4:12b"  # или "qwen2.5:14b"
    test_prompt = "Реши задачу: 2+2*2. Объясни шаги."
    test_think_option(model, test_prompt)