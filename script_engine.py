import random
CURATED_SCRIPTS = {
    "police_ai": {
        "title": "GTA 6 Police AI is Actually Insane",
        "text": "GTA 6 police AI is going to ruin your life, and here is why! Unlike GTA 5 where cops spawn out of thin air behind you, Rockstar has patented a brand new patrol system. Police will now remember your car model, memorize your license plate, and set up realistic roadblocks ahead of your route. If you commit a crime with no witnesses, you won't even get a wanted level! Do you think this makes the game better or too realistic? Comment down below!"
    },
    "water_physics": {
        "title": "GTA 6 Water Physics Will Melt Your Mind",
        "text": "Rockstar spent twenty engineers just on water physics for GTA 6! Vice City is surrounded by beaches, and the wave simulation actually reacts to wind direction and incoming storm surges in real time. Boats will handle completely differently depending on the tide, and high-speed impacts with waves can literally tear your vehicle apart. Are you exploring the ocean first, or heading straight into the city?"
    },
    "enterable_buildings": {
        "title": "How Many Buildings Can You Enter in GTA 6?",
        "text": "Did you know GTA 6 will have more enterable buildings than every previous GTA combined? Leaked data suggests over seventy percent of shops, clubs, and residential apartments can actually be walked into with fully decorated interiors! You can rob pawn shops, sneak into hotel rooms, or hide out inside supermarkets during police chases. What building are you breaking into first?"
    }
}
def get_script(k=None): return CURATED_SCRIPTS.get(k) or CURATED_SCRIPTS[random.choice(list(CURATED_SCRIPTS.keys()))]
def list_topics(): return list(CURATED_SCRIPTS.keys())
