# 3-Way Model Comparison: Haiku 4.5 vs Gemini 3 Flash vs Gemini 2.5 Flash Lite

Date: 2026-02-22 21:45

Flash Lite model: `gemini-2.5-flash-lite`

---

## ESPRI (`rich` -- id=3686)

README: 7,256 chars | Tree: 185 entries

| Metric | Flash Lite |
|--------|------------|
| Latency | 5.3s |
| Input tokens | 9,512 |
| Output tokens | 1,601 |
| JSON parsed | Y |

| Field | Haiku 4.5 | Gemini 3 Flash | Flash Lite | H=FL | G=FL |
|-------|-----------|----------------|------------|------|------|
| Project type | mixed | mixed | mixed | Y | Y |
| Structure quality | well_structured | well_structured | well_structured | Y | Y |
| Doc location | inline | inline | inline | Y | Y |
| License present | True | True | True | Y | Y |
| License type | explicit | explicit | explicit | Y | Y |
| License name | Apache License 2.0 | Apache License 2.0 | Apache License 2.0 | Y | Y |
| Contributing present | True | True | True | Y | Y |
| Contributing level | 1 | 1 | 1 | Y | Y |
| BOM present | True | True | True | Y | Y |
| BOM completeness | partial | partial | partial | Y | Y |
| BOM component count | 0 | 0 | 0 | Y | Y |
| Assembly present | False | False | False | Y | Y |
| Assembly detail | none | none | none | Y | Y |
| Assembly step count | 0 | 0 | 0 | Y | Y |
| HW design present | True | True | True | Y | Y |
| HW design types | ['PCB_Layout', 'Circuit_Schematic'] | ['PCB_Layout', 'Circuit_Schematic'] | ['Circuit_Schematic'] | **N** | **N** |
| HW editable src | False | False | False | Y | Y |
| Mech design present | False | False | False | Y | Y |
| Mech design types | [] | [] | [] | Y | Y |
| Mech editable src | False | False | False | Y | Y |
| SW/FW present | True | True | True | Y | Y |
| SW/FW type | firmware | firmware | firmware | Y | Y |
| SW/FW frameworks | ['ESP-IDF'] | ['ESP-IDF'] | ['ESP-IDF'] | Y | Y |
| SW/FW doc level | basic | complete | basic | Y | **N** |
| Testing present | False | False | False | Y | Y |
| Testing detail | none | none | none | Y | Y |
| Cost mentioned | False | False | False | Y | Y |
| Suppliers ref'd | False | False | False | Y | Y |
| Part numbers | True | True | False | **N** | **N** |
| Maturity stage | unstated | unstated | prototype | **N** | **N** |
| HW license present | False | False | False | Y | Y |
| HW license name | None | None | None | Y | Y |
| SW license present | True | True | True | Y | Y |
| SW license name | Apache License 2.0 | Apache License 2.0 | Apache License 2.0 | Y | Y |
| Doc license present | False | False | False | Y | Y |
| Doc license name | None | None | None | Y | Y |

**Haiku vs Flash Lite: 33/36 (92%)**
**Gemini 3 vs Flash Lite: 32/36 (89%)**

---

## Dact nano (`medium` -- id=2622)

README: 601 chars | Tree: 62 entries

| Metric | Flash Lite |
|--------|------------|
| Latency | 3.6s |
| Input tokens | 7,093 |
| Output tokens | 1,257 |
| JSON parsed | Y |

| Field | Haiku 4.5 | Gemini 3 Flash | Flash Lite | H=FL | G=FL |
|-------|-----------|----------------|------------|------|------|
| Project type | hardware | hardware | hardware | Y | Y |
| Structure quality | basic | basic | well_structured | **N** | **N** |
| Doc location | inline | inline | inline | Y | Y |
| License present | True | True | True | Y | Y |
| License type | explicit | explicit | explicit | Y | Y |
| License name | CERN-OHL-P | CERN-OHL-P | CERN-OHL-P | Y | Y |
| Contributing present | False | False | False | Y | Y |
| Contributing level | 0 | 0 | 0 | Y | Y |
| BOM present | True | True | True | Y | Y |
| BOM completeness | partial | partial | partial | Y | Y |
| BOM component count | 0 | 0 | 0 | Y | Y |
| Assembly present | False | False | False | Y | Y |
| Assembly detail | none | none | none | Y | Y |
| Assembly step count | 0 | 0 | 0 | Y | Y |
| HW design present | True | True | True | Y | Y |
| HW design types | ['PCB_Layout', 'Circuit_Schematic'] | ['PCB_Layout', 'Circuit_Schematic'] | ['PCB_Layout', 'Circuit_Schematic'] | Y | Y |
| HW editable src | True | True | True | Y | Y |
| Mech design present | True | True | True | Y | Y |
| Mech design types | ['CAD'] | ['CAD'] | ['CAD'] | Y | Y |
| Mech editable src | True | True | True | Y | Y |
| SW/FW present | False | False | False | Y | Y |
| SW/FW type | none | none | none | Y | Y |
| SW/FW frameworks | [] | [] | [] | Y | Y |
| SW/FW doc level | none | none | none | Y | Y |
| Testing present | False | False | False | Y | Y |
| Testing detail | none | none | none | Y | Y |
| Cost mentioned | False | False | False | Y | Y |
| Suppliers ref'd | False | False | False | Y | Y |
| Part numbers | False | False | False | Y | Y |
| Maturity stage | unstated | unstated | unstated | Y | Y |
| HW license present | True | True | True | Y | Y |
| HW license name | CERN-OHL-P | CERN-OHL-P | CERN-OHL-P | Y | Y |
| SW license present | False | False | False | Y | Y |
| SW license name | None | None | None | Y | Y |
| Doc license present | False | False | False | Y | Y |
| Doc license name | None | None | None | Y | Y |

**Haiku vs Flash Lite: 35/36 (97%)**
**Gemini 3 vs Flash Lite: 35/36 (97%)**

---

## Fresh air automation by RF usb dongle (`sparse` -- id=4716)

README: 64 chars | Tree: 1 entries

| Metric | Flash Lite |
|--------|------------|
| Latency | 3.1s |
| Input tokens | 6,030 |
| Output tokens | 976 |
| JSON parsed | Y |

| Field | Haiku 4.5 | Gemini 3 Flash | Flash Lite | H=FL | G=FL |
|-------|-----------|----------------|------------|------|------|
| Project type | unclear | unclear | unclear | Y | Y |
| Structure quality | poor | poor | poor | Y | Y |
| Doc location | redirect | redirect | redirect | Y | Y |
| License present | False | False | False | Y | Y |
| License type | none | none | none | Y | Y |
| License name | None | None | None | Y | Y |
| Contributing present | False | False | False | Y | Y |
| Contributing level | 0 | 0 | 0 | Y | Y |
| BOM present | False | False | False | Y | Y |
| BOM completeness | none | none | none | Y | Y |
| BOM component count | 0 | 0 | 0 | Y | Y |
| Assembly present | False | False | False | Y | Y |
| Assembly detail | none | none | none | Y | Y |
| Assembly step count | 0 | 0 | 0 | Y | Y |
| HW design present | False | False | False | Y | Y |
| HW design types | [] | [] | [] | Y | Y |
| HW editable src | False | False | False | Y | Y |
| Mech design present | False | False | False | Y | Y |
| Mech design types | [] | [] | [] | Y | Y |
| Mech editable src | False | False | False | Y | Y |
| SW/FW present | False | False | False | Y | Y |
| SW/FW type | none | none | none | Y | Y |
| SW/FW frameworks | [] | [] | [] | Y | Y |
| SW/FW doc level | none | none | none | Y | Y |
| Testing present | False | False | False | Y | Y |
| Testing detail | none | none | none | Y | Y |
| Cost mentioned | False | False | False | Y | Y |
| Suppliers ref'd | False | False | False | Y | Y |
| Part numbers | False | False | False | Y | Y |
| Maturity stage | unstated | unstated | unstated | Y | Y |
| HW license present | False | False | False | Y | Y |
| HW license name | None | None | None | Y | Y |
| SW license present | False | False | False | Y | Y |
| SW license name | None | None | None | Y | Y |
| Doc license present | False | False | False | Y | Y |
| Doc license name | None | None | None | Y | Y |

**Haiku vs Flash Lite: 36/36 (100%)**
**Gemini 3 vs Flash Lite: 36/36 (100%)**

---

## NASA-JPL Open-Source Rover (`testing` -- id=7346)

README: 12,357 chars | Tree: 1,072 entries

| Metric | Flash Lite |
|--------|------------|
| Latency | 4.0s |
| Input tokens | 12,987 |
| Output tokens | 1,717 |
| JSON parsed | Y |

| Field | Haiku 4.5 | Gemini 3 Flash | Flash Lite | H=FL | G=FL |
|-------|-----------|----------------|------------|------|------|
| Project type | hardware | mixed | hardware | Y | **N** |
| Structure quality | well_structured | well_structured | well_structured | Y | Y |
| Doc location | inline | inline | inline | Y | Y |
| License present | True | True | True | Y | Y |
| License type | referenced | explicit | file reference | **N** | **N** |
| License name | None | Open-Source Hardware certified (OSHWA US002551) | LICENSE.txt | **N** | **N** |
| Contributing present | True | True | True | Y | Y |
| Contributing level | 2 | 2 | 1 | **N** | **N** |
| BOM present | True | True | True | Y | Y |
| BOM completeness | partial | partial | partial | Y | Y |
| BOM component count | 0 | 0 | 0 | Y | Y |
| Assembly present | True | True | True | Y | Y |
| Assembly detail | referenced | referenced | referenced | Y | Y |
| Assembly step count | 0 | 0 | 0 | Y | Y |
| HW design present | True | True | True | Y | Y |
| HW design types | ['PCB_Layout', 'Circuit_Schematic'] | ['PCB_Layout', 'Circuit_Schematic'] | ['PCB_Layout', 'Circuit_Schematic'] | Y | Y |
| HW editable src | True | True | True | Y | Y |
| Mech design present | True | True | True | Y | Y |
| Mech design types | ['CAD'] | ['CAD'] | ['CAD', '3D_Printable'] | **N** | **N** |
| Mech editable src | True | True | True | Y | Y |
| SW/FW present | True | True | True | Y | Y |
| SW/FW type | control_software | control_software | control_software | Y | Y |
| SW/FW frameworks | ['ROS'] | ['ROS'] | [] | **N** | **N** |
| SW/FW doc level | referenced | referenced | referenced | Y | Y |
| Testing present | False | True | True | **N** | Y |
| Testing detail | none | basic | basic | **N** | Y |
| Cost mentioned | True | True | True | Y | Y |
| Suppliers ref'd | True | True | True | Y | Y |
| Part numbers | False | True | True | **N** | Y |
| Maturity stage | production | production | production | Y | Y |
| HW license present | False | True | False | Y | **N** |
| HW license name | None | OSHWA certified | None | Y | **N** |
| SW license present | False | False | False | Y | Y |
| SW license name | None | None | None | Y | Y |
| Doc license present | False | False | False | Y | Y |
| Doc license name | None | None | None | Y | Y |

**Haiku vs Flash Lite: 28/36 (78%)**
**Gemini 3 vs Flash Lite: 28/36 (78%)**

---

## Cost Summary

| Metric | Value |
|--------|-------|
| Total input tokens | 35,622 |
| Total output tokens | 5,551 |
| Cost (4 projects) | $0.0029 |
| Extrapolated (7,057 projects) | $5.10 |
