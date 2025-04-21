import os
import subprocess
import re 
import requests
import typer
from dotenv import load_dotenv
from typing import Optional
import platform

IS_WINDOWS = platform.system() == "Windows"
load_dotenv()
app = typer.Typer()

API_URL = "https://api-inference.huggingface.co/models/codellama/CodeLlama-7b-hf"
HEADERS = {"Authorization": f"Bearer {os.getenv('HF_API_KEY')}"}
BLOCKED_COMMANDS = ["rm -rf", "format"]

def query_ai(prompt: str ) -> str:
    """Query Hugging Face API and return generated commands."""
    try:
        payload = {
        "inputs": f"Generate { 'Windows CMD' if IS_WINDOWS else 'bash' } and ONE safe terminal command to: {prompt}. Return only commands in a code block.",
        "parameters": {"max_new_tokens": 200}
        }

        response = requests.post(API_URL, headers=HEADERS, json=payload, timeout=30)
        response.raise_for_status()

        return response.json()[0]["generated_text"]
    except requests.exceptions.RequestException as e:
        typer.secho(f"API Error: {str(e)}", fg="red")

        return ""
    
def extract_commands( ai_response: str ) -> list:
    """Extract commands from markdown code blocks."""
    matches = re.findall(r"```(?:bash|sh|cmd|powershell)?\n(.*?)\n```", ai_response, re.DOTALL)

    commands = []
    for block in matches:
        commands.extend([cmd.strip() for cmd in block.split("\n") if cmd.strip()])
    return commands

def validate_commands(commands: list) -> bool:
    """Check for dangerous commands."""
    for cmd in commands:

        if ("\\" in cmd and not IS_WINDOWS) or ("/" in cmd and IS_WINDOWS):
            typer.secho(f"OS mismatch: {cmd}", fg="red")
            return False
        
        if any( banned in cmd for banned in BLOCKED_COMMANDS ):
            typer.secho(f"Blocked cmd command: {cmd}", fg="red")
            return False
    return True 
    
@app.command()
def chat(max_retries: Optional[int] = typer.Option(default=3, help="maximum retry attempts")):
    """Main chat interface."""
    typer.secho("\nAI Task Agent (type 'exit' to quit)\n", fg="blue", bold=True)

    retry_count = 0
    while retry_count < max_retries:
        task = typer.prompt("Enter task").strip()

        if task.lower() == "exit":
            typer.secho("Exiting...",fg="yellow")
            return
        
        ai_response = query_ai(task)
        commands = extract_commands(ai_response)

        if not commands:
            typer.secho("No valid commands generated. Please try again.", fg="yellow")
            continue

        # Display generated plan
        typer.secho("\nGenerated Plan:", fg="green")

        for i, cmd in enumerate(commands, 1):
            typer.echo(f"  {i}. {cmd}")

        # Safety check
        if not validate_commands(commands):
            typer.secho("Aborting due to dangerous commands!", fg="red")
            continue

        if not typer.confirm("\nExecute these commands?"):
            continue

        full_command = " && ".join(commands)

        success = True
        for cmd in commands :
            try:
                result = subprocess.run(
                    full_command,  # Execute all commands as one
                    shell=True,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                if result.stdout:
                    typer.secho(f"Output:\n{result.stdout}", fg="white")
            except subprocess.CalledProcessError as e:
                typer.secho(f"\nError executing command: {cmd}", fg="red")
                typer.secho(f"Error details:\n{e.stderr}", fg="red")
                success = False
                break
        
        if success and typer.confirm("\nTask completed successfully!"):
            typer.secho("Success!", fg="green")
            return
        else:
            retry_count += 1
            if retry_count < max_retries:
                feedback = typer.prompt("What went wrong?")
                task = f"{task}. Previous error: {feedback}"
                typer.secho(f"Retrying ({retry_count}/{max_retries})...\n", fg="yellow")

    typer.secho("\nMaximum retries exceeded. Exiting.", fg="red")

if __name__ == "__main__":
    app()
