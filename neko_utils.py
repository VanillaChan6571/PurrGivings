import os
import json
import sys
import re
from datetime import timedelta, datetime

def get_token():
    config_file = 'bot-config.json'
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            config = json.load(f)
            return config.get('token')
    else:
        while True:
            sys.stdout.write("Please enter your Discord bot token: ")
            sys.stdout.flush()
            token = input().strip()

            if len(token) < 50:
                print("Error: Token is too short. Discord bot tokens are usually 50+ characters long. Please try again.")
            else:
                with open(config_file, 'w') as f:
                    json.dump({'token': token}, f)
                print(f"Token saved to {config_file}")
                return token

def parse_time(time_str):
    total_seconds = 0
    time_units = {'w': 7 * 24 * 60 * 60, 'd': 24 * 60 * 60, 'h': 60 * 60, 'm': 60, 's': 1}
    pattern = re.compile(r'(\d+)([wdhms])')

    for value, unit in pattern.findall(time_str):
        total_seconds += int(value) * time_units[unit]

    return timedelta(seconds=total_seconds)

def generate_giveaway_id(conn):
    year = datetime.now().year
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM giveaways WHERE id LIKE ?", (f'%-{year}',))
    count = cursor.fetchone()[0] + 1
    return f'N{count:03d}-{year}'

def format_time_remaining(time_remaining):
    days, remainder = divmod(time_remaining.total_seconds(), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(days)}d {int(hours)}h {int(minutes)}m {int(seconds)}s"

def is_valid_image_url(url):
    # This is a basic check. You might want to improve it based on your needs.
    return url.startswith('http') and any(url.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif'])

def sanitize_input(input_string):
    # Remove any potentially harmful characters
    return re.sub(r'[^\w\s-]', '', input_string).strip()

def load_config(config_file='config.json'):
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            return json.load(f)
    else:
        return {}

def save_config(config, config_file='config.json'):
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=4)

def validate_giveaway_params(title, length, winners):
    errors = []
    if len(title) > 256:
        errors.append("Title must be 256 characters or less.")
    if not re.match(r'^(\d+[wdhms])+$', length):
        errors.append("Invalid time format. Use combinations of w (weeks), d (days), h (hours), m (minutes), s (seconds).")
    if winners < 1:
        errors.append("Number of winners must be at least 1.")
    return errors