import os

# 1. Put the folder name where your cogs are stored
COGS_FOLDER = './cogs' 

# 2. Dictionary mapping the old emojis to your new custom ones
EMOJI_REPLACEMENTS = {
    "📜": "<:BlueScroll:1489151045933207643>",
    "🎉": "<a:prizes:1489156992512557216>",
    "✅": "<a:tick:1489157731393994854>",
    "📂": "<:folder:1489151375077150810>",
    "⬅️": "<a:arrow_lefts:1489152047633797131>",
    "➡️": "<a:side_arrow_2:1489151786903408865>",
    "👥": "<a:users:1489162870057865336>",
    "🎁": "<a:gift_:1489165623165583371>",
    "❌": "<a:Cross_:1489174755537064046>",
    "⚠️": "<a:Alert1:1489188698191822908>",
    "👢": "<a:Kick:1489189035736825866>",
    "🏓": "<a:minecraft_block:1489165065566421104>"
}

def replace_emojis():
    files_changed = 0

    # Go through every file in the cogs folder
    for filename in os.listdir(COGS_FOLDER):
        if filename.endswith('.py'):
            filepath = os.path.join(COGS_FOLDER, filename)
            
            # Read the file
            with open(filepath, 'r', encoding='utf-8') as file:
                code = file.read()
            
            original_code = code

            # Loop through our dictionary and replace each emoji
            for old_emoji, new_emoji in EMOJI_REPLACEMENTS.items():
                code = code.replace(old_emoji, new_emoji)
            
            # If the code changed, save the file
            if code != original_code:
                with open(filepath, 'w', encoding='utf-8') as file:
                    file.write(code)
                print(f"✅ Updated emojis in {filename}")
                files_changed += 1

    print(f"\nDone! Successfully updated {files_changed} file(s).")

# Run the function
replace_emojis()