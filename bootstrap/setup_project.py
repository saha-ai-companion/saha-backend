from pathlib import Path

folders = [
    "app",
    "app/api",
    "app/core",
    "app/db",
    "app/models",
    "app/services",
    "app/schemas",
    "tests",
    "docs",
    "scripts",
]

files = {
    "app/main.py": """from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"status": "Backend Running"}
""",

    "requirements.txt": "",
    
    ".env.example": "APP_ENV=development",
    
    ".gitignore": "__pycache__/\nvenv/\n.env",
    
    "README.md": "# Saha Backend"
}

def create_structure():
    for folder in folders:
        Path(folder).mkdir(parents=True, exist_ok=True)

    for file_path, content in files.items():
        path = Path(file_path)

        if not path.exists():
            path.write_text(content)

if __name__ == "__main__":
    create_structure()