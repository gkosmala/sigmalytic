from pathlib import Path

path = Path("backend/evidence/weis_gamma_fusion_engine.py")
text = path.read_text(encoding="utf-8")

old = '''        elif theta_flush_risk:
            fusion_state = "THETA_FLUSH_RISK"
            fusion_direction = "RISK"
            base_confidence = 0.65
            reason = "0DTE activity is elevated while wave efficiency is stalling late in the session."
'''

new = '''        elif not gamma_data_fresh:
            fusion_state = "WEIS_ONLY_GAMMA_STALE"
            fusion_direction = wave_direction if wave_direction in {"UP", "DOWN"} else "UNKNOWN"
            base_confidence = 0.40
            reason = "Weis evidence exists, but Gamma data is stale. Gamma cannot confirm the phase."

        elif theta_flush_risk:
            fusion_state = "THETA_FLUSH_RISK"
            fusion_direction = "RISK"
            base_confidence = 0.65
            reason = "0DTE activity is elevated while wave efficiency is stalling late in the session."
'''

if old not in text:
    raise SystemExit("Could not find theta_flush_risk branch for insertion.")

text = text.replace(old, new, 1)

old_stale_block = '''        elif not gamma_data_fresh:
            fusion_state = "WEIS_ONLY_GAMMA_STALE"
            fusion_direction = wave_direction if wave_direction in {"UP", "DOWN"} else "UNKNOWN"
            base_confidence = 0.40
            reason = "Weis evidence exists, but Gamma data is stale. Gamma cannot confirm the phase."

'''

# Remove the later duplicate stale block, leaving the new early stale block.
first = text.find(old_stale_block)
second = text.find(old_stale_block, first + len(old_stale_block))

if second != -1:
    text = text[:second] + text[second + len(old_stale_block):]

path.write_text(text, encoding="utf-8")
print("Patched stale Gamma branch order.")
