from dotenv import load_dotenv

load_dotenv()

from app import create_app  # noqa: E402  (musi być po load_dotenv())

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, port=5001)
