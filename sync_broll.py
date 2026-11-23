#!/usr/bin/env python3
import os, sys, glob, shutil, argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
BROLL_DIR = os.path.join(DOWNLOADS_DIR, "broll")
RAW_GAMEPLAY_DIR = os.path.join(BROLL_DIR, "raw_gameplay")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

for d in [DOWNLOADS_DIR, BROLL_DIR, RAW_GAMEPLAY_DIR, OUTPUT_DIR]:
    os.makedirs(d, exist_ok=True)

CURATED_CLIPS = {
    "ext_clip_05_dynamic_storm_surge.mp4": "water", "ext_clip_08_beach_crowd_ai.mp4": "water",
    "ext_clip_09_airboat_swamp_drift.mp4": "water", "ext_clip_16_yacht_party_water.mp4": "water",
    "ext_clip_19_swamp_wildlife.mp4": "water", "clip_01_ocean_speedboats.mp4": "water",
    "clip_02_beach_drones.mp4": "water", "clip_05_everglades_airboat.mp4": "water",
    "t2_clip_08_swamp_hovercraft.mp4": "water", "clip_09_thrillbilly_mud.mp4": "water",
    "clip_11_police_sirens.mp4": "police", "t2_clip_07_highway_police_chase.mp4": "police",
    "t2_clip_12_helicopter_spotlight.mp4": "police", "t2_clip_15_armored_truck_escape.mp4": "police",
    "ext_clip_06_police_helicopter_search.mp4": "police", "ext_clip_15_police_spike_strip.mp4": "police",
    "clip_08_lowriders_meet.mp4": "cars", "clip_10_dirtbikes_gang.mp4": "cars",
    "clip_13_convertible_cruise.mp4": "cars", "t2_clip_03_sports_car_drift.mp4": "cars",
    "t2_clip_10_dirt_track_buggy.mp4": "cars", "t2_clip_11_motorcycle_escape.mp4": "cars",
    "ext_clip_02_car_customization.mp4": "cars", "ext_clip_11_jason_highway_cruise.mp4": "cars",
    "ext_clip_14_speeding_convertible.mp4": "cars", "ext_clip_20_sunset_bridge_traffic.mp4": "cars",
    "clip_14_store_robbery.mp4": "heist", "t2_clip_05_heist_prep_weapons.mp4": "heist",
    "t2_clip_06_bank_vault_breach.mp4": "heist", "t2_clip_14_shootout_gas_station.mp4": "heist",
    "ext_clip_04_gun_shop_inspection.mp4": "heist", "ext_clip_12_gas_station_clerk.mp4": "heist",
    "ext_clip_18_convenience_store_loot.mp4": "heist", "clip_03_flamingos_highway.mp4": "city",
    "clip_04_bridge_to_city.mp4": "city", "clip_06_rooftop_pool.mp4": "city",
    "clip_07_ocean_drive_neon.mp4": "city", "clip_12_nightclub_party.mp4": "city",
    "t2_clip_01_jason_lucia_intro.mp4": "city", "t2_clip_02_vice_city_skyline.mp4": "city",
    "t2_clip_04_port_gellhorn_docks.mp4": "city", "t2_clip_09_strip_club_neon.mp4": "city",
    "t2_clip_13_luxury_mansion_pool.mp4": "city", "t2_clip_16_lucia_jason_climax.mp4": "city",
    "ext_clip_01_mall_interior.mp4": "city", "ext_clip_03_tennis_physics.mp4": "city",
    "ext_clip_07_night_neon_traffic.mp4": "city", "ext_clip_10_lucia_motel_cutscene.mp4": "city",
    "ext_clip_13_club_volumetric_fog.mp4": "city", "ext_clip_17_pedestrian_reaction.mp4": "city"
}

def classify(fn):
    b = os.path.basename(fn.lower())
    if b in CURATED_CLIPS: return CURATED_CLIPS[b]
    if b.startswith("water_"): return "water"
    if b.startswith("police_"): return "police"
    if b.startswith("cars_"): return "cars"
    if b.startswith("heist_"): return "heist"
    if b.startswith("city_"): return "city"
    if b.startswith("action_gameplay_"): return "gameplay"
    if any(k in b for k in ['police','cop','chase','spike','sirens','spotlight']): return "police"
    if any(k in b for k in ['robbery','vault','heist','weapons','shootout','loot']): return "heist"
    if any(k in b for k in ['water','boat','airboat','hovercraft','swamp','beach','storm','wave']): return "water"
    if any(k in b for k in ['car','drift','drive','cruise','speeding','buggy']): return "cars"
    return "city"

def run_sync(clean_out=False):
    all_b = [f for f in glob.glob(os.path.join(BROLL_DIR, "*.mp4")) if os.path.getsize(f) > 50000]
    cats = {}
    for b in all_b:
        c = classify(b)
        cats.setdefault(c, []).append(b)

    print("\n" + "=" * 65)
    print("📊 AKTUÁLNÍ STAV TÉMATICKÉ B-ROLL KNIHOVNY")
    print("=" * 65)
    labels = {
        "water": "🌊 WATER (Hurikány, záplavy, bažiny, lodě)",
        "police": "🚨 POLICE (Honitby, majáky, vrtulníky)",
        "cars": "🚗 CARS (Drift, tuning, dálniční jízda)",
        "heist": "💥 HEIST (Loupeže, přestřelky, zbraně)",
        "city": "🌆 CITY (Skyline, neonové kluby, nákupní centra)"
    }
    for k in ["water", "police", "cars", "heist", "city"]:
        cnt = len(cats.get(k, []))
        st = "✅ PŘIPRAVENO" if cnt >= 3 else "⚠️ MÁLO KLIPŮ"
        print(f" {labels[k]:<48} : {cnt:>3} klipů [{st}]")

    total_curated = sum(len(cats.get(k, [])) for k in ["water", "police", "cars", "heist", "city"])
    print("-" * 65)
    print(f" CELKEM KURÁTOROVANÝCH KLIPŮ: {total_curated}")
    print(f" Složka: {BROLL_DIR}")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    run_sync()
