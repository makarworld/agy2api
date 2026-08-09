import os
from openai import OpenAI

# Initialize the OpenAI client pointing to the local AGY2API wrapper
client = OpenAI(
    base_url="http://localhost:8000/v1",
    # Pass your configured AGY_API_KEY here
    api_key=os.environ.get("AGY_API_KEY", "your-secret-key-here")
)

def main():
    print("Sending chat completion request to AGY2API...")
    
    # You can specify "Gemini 3.6 Flash (High)" or any other supported model
    response = client.chat.completions.create(
        model="Gemini 3.6 Flash (High)",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Write a short haiku about coding."}
        ]
    )

    print("\nResponse:")
    print("-" * 20)
    print(response.choices[0].message.content)
    print("-" * 20)

if __name__ == "__main__":
    main()
