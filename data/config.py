from environs import Env

# Use the environs library
env = Env()
env.read_env()

# Read the following from the .env file
BOT_TOKEN = env.str("BOT_TOKEN")  # Bot token
ADMINS = env.list("ADMINS")  # List of admins
IP = env.str("ip", "localhost")  # Hosting IP address
ANTHROPIC_API_KEY = env.str("ANTHROPIC_API_KEY", "")  # Chart screenshot analysis (optional)
DB_PATH = env.str("DB_PATH", "")  # SQLite file; set it to a mounted volume in production
