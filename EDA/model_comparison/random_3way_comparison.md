# 3-Way Model Comparison: Random Sample (n=10 (seed=42))

Date: 2026-02-22 22:10

| Model | ID |
|-------|----|
| Haiku 4.5 | `claude-haiku-4-5-20251001` |
| Gemini 3 Flash | `gemini-3-flash-preview` |
| Flash Lite | `gemini-2.5-flash-lite` |

---

## 1. pic0rick (id=7643)

README: 4,293 chars | Tree: 1,866 entries

| Metric | Haiku | Gemini 3 | Flash Lite |
|--------|-------|----------|------------|
| Latency | 21.1s | 17.8s | 7.2s |
| Input tok | 13,031 | 12,818 | 12,818 |
| Output tok | 2,814 | 1,732 | 2,464 |
| JSON OK | Y | Y | Y |

| Field | Haiku | Gemini 3 | Flash Lite | H=G | H=FL | G=FL | All |
|-------|-------|----------|------------|-----|------|------|-----|
| Project type | hardware | mixed | hardware | **N** | Y | **N** | **N** |
| Structure quality | well_structured | well_structured | well_structured | Y | Y | Y | Y |
| Doc location | inline | inline | inline | Y | Y | Y | Y |
| License present | True | True | True | Y | Y | Y | Y |
| License type | explicit | explicit | explicit | Y | Y | Y | Y |
| License name | Multiple: TAPR-OHL, GPL-3.0, CC-BY-SA-3.0 | TAPR-OHL, GPL-3.0, CC-BY-SA-3.0 | Multiple: TAPR OHL, GPL, CC BY-SA | **N** | **N** | **N** | **N** |
| Contributing present | False | False | False | Y | Y | Y | Y |
| Contributing level | 0 | 0 | 0 | Y | Y | Y | Y |
| BOM present | True | True | True | Y | Y | Y | Y |
| BOM completeness | partial | partial | partial | Y | Y | Y | Y |
| BOM component count | 0 | 0 | 0 | Y | Y | Y | Y |
| Assembly present | False | False | False | Y | Y | Y | Y |
| Assembly detail | none | none | none | Y | Y | Y | Y |
| Assembly step count | 0 | 0 | 0 | Y | Y | Y | Y |
| HW design present | True | True | True | Y | Y | Y | Y |
| HW design types | ['PCB_Layout', 'Circuit_Schematic'] | ['PCB_Layout', 'Circuit_Schematic', 'Electronic_Component'] | ['PCB_Layout', 'Circuit_Schematic', 'Electronic_Component'] | **N** | **N** | Y | **N** |
| HW editable src | True | True | True | Y | Y | Y | Y |
| Mech design present | True | True | True | Y | Y | Y | Y |
| Mech design types | ['CAD'] | ['CAD'] | ['CAD'] | Y | Y | Y | Y |
| Mech editable src | True | True | True | Y | Y | Y | Y |
| SW/FW present | True | True | True | Y | Y | Y | Y |
| SW/FW type | firmware | firmware | firmware | Y | Y | Y | Y |
| SW/FW frameworks | ['Pico SDK', 'PlatformIO'] | ['Raspberry Pi Pico SDK'] | ['Pico SDK', 'PIO'] | **N** | **N** | **N** | **N** |
| SW/FW doc level | basic | basic | basic | Y | Y | Y | Y |
| Testing present | False | False | True | Y | **N** | **N** | **N** |
| Testing detail | none | none | basic | Y | **N** | **N** | **N** |
| Cost mentioned | False | False | False | Y | Y | Y | Y |
| Suppliers ref'd | False | False | False | Y | Y | Y | Y |
| Part numbers | True | True | True | Y | Y | Y | Y |
| Maturity stage | unstated | prototype | prototype | **N** | **N** | Y | **N** |
| HW license present | True | True | True | Y | Y | Y | Y |
| HW license name | TAPR Open Hardware License | TAPR Open Hardware License | TAPR Open Hardware License | Y | Y | Y | Y |
| SW license present | True | True | True | Y | Y | Y | Y |
| SW license name | GNU General Public License v3.0 | GNU General Public License v3.0 | GNU General Public License v3.0 | Y | Y | Y | Y |
| Doc license present | True | True | True | Y | Y | Y | Y |
| Doc license name | Creative Commons Attribution-ShareAlike 3.0 Unported License | Creative Commons Attribution-ShareAlike 3.0 Unported License | Creative Commons Attribution-ShareAlike 3.0 Unported License | Y | Y | Y | Y |

| **Totals** | | | | **31/36 (86%)** | **30/36 (83%)** | **31/36 (86%)** | **29/36 (81%)** |

---

## 2. D&D Teensy (id=1244)

README: 377 chars | Tree: 19 entries

| Metric | Haiku | Gemini 3 | Flash Lite |
|--------|-------|----------|------------|
| Latency | 13.4s | 14.5s | 3.5s |
| Input tok | 6,649 | 6,400 | 6,400 |
| Output tok | 1,693 | 1,206 | 1,269 |
| JSON OK | Y | Y | Y |

| Field | Haiku | Gemini 3 | Flash Lite | H=G | H=FL | G=FL | All |
|-------|-------|----------|------------|-----|------|------|-----|
| Project type | hardware | mixed | hardware | **N** | Y | **N** | **N** |
| Structure quality | basic | basic | basic | Y | Y | Y | Y |
| Doc location | inline | inline | inline | Y | Y | Y | Y |
| License present | False | False | False | Y | Y | Y | Y |
| License type | none | none | none | Y | Y | Y | Y |
| License name | None | None | None | Y | Y | Y | Y |
| Contributing present | False | False | False | Y | Y | Y | Y |
| Contributing level | 0 | 0 | 0 | Y | Y | Y | Y |
| BOM present | False | False | False | Y | Y | Y | Y |
| BOM completeness | none | none | none | Y | Y | Y | Y |
| BOM component count | 0 | 0 | 0 | Y | Y | Y | Y |
| Assembly present | False | False | False | Y | Y | Y | Y |
| Assembly detail | none | none | none | Y | Y | Y | Y |
| Assembly step count | 0 | 0 | 0 | Y | Y | Y | Y |
| HW design present | True | True | True | Y | Y | Y | Y |
| HW design types | ['PCB_Layout', 'Circuit_Schematic'] | ['PCB_Layout', 'Circuit_Schematic'] | ['PCB_Layout'] | Y | **N** | **N** | **N** |
| HW editable src | False | False | False | Y | Y | Y | Y |
| Mech design present | False | False | False | Y | Y | Y | Y |
| Mech design types | [] | [] | [] | Y | Y | Y | Y |
| Mech editable src | False | False | False | Y | Y | Y | Y |
| SW/FW present | True | True | True | Y | Y | Y | Y |
| SW/FW type | firmware | firmware | firmware | Y | Y | Y | Y |
| SW/FW frameworks | ['Arduino'] | ['Arduino'] | ['Arduino'] | Y | Y | Y | Y |
| SW/FW doc level | basic | none | none | **N** | **N** | Y | **N** |
| Testing present | False | False | False | Y | Y | Y | Y |
| Testing detail | none | none | none | Y | Y | Y | Y |
| Cost mentioned | False | False | False | Y | Y | Y | Y |
| Suppliers ref'd | False | False | False | Y | Y | Y | Y |
| Part numbers | False | False | False | Y | Y | Y | Y |
| Maturity stage | unstated | unstated | unstated | Y | Y | Y | Y |
| HW license present | False | False | False | Y | Y | Y | Y |
| HW license name | None | None | None | Y | Y | Y | Y |
| SW license present | False | False | False | Y | Y | Y | Y |
| SW license name | None | None | None | Y | Y | Y | Y |
| Doc license present | False | False | False | Y | Y | Y | Y |
| Doc license name | None | None | None | Y | Y | Y | Y |

| **Totals** | | | | **34/36 (94%)** | **34/36 (94%)** | **34/36 (94%)** | **33/36 (92%)** |

---

## 3. 32xe (id=273)

README: 696 chars | Tree: 26 entries

| Metric | Haiku | Gemini 3 | Flash Lite |
|--------|-------|----------|------------|
| Latency | 12.3s | 13.0s | 4.3s |
| Input tok | 6,660 | 6,424 | 6,424 |
| Output tok | 1,397 | 1,182 | 1,347 |
| JSON OK | Y | Y | Y |

| Field | Haiku | Gemini 3 | Flash Lite | H=G | H=FL | G=FL | All |
|-------|-------|----------|------------|-----|------|------|-----|
| Project type | mixed | mixed | mixed | Y | Y | Y | Y |
| Structure quality | basic | basic | well_structured | Y | **N** | **N** | **N** |
| Doc location | inline | inline | inline | Y | Y | Y | Y |
| License present | False | False | False | Y | Y | Y | Y |
| License type | none | none | none | Y | Y | Y | Y |
| License name | None | None | None | Y | Y | Y | Y |
| Contributing present | False | False | False | Y | Y | Y | Y |
| Contributing level | 0 | 0 | 0 | Y | Y | Y | Y |
| BOM present | False | False | False | Y | Y | Y | Y |
| BOM completeness | none | none | none | Y | Y | Y | Y |
| BOM component count | 0 | 0 | 0 | Y | Y | Y | Y |
| Assembly present | False | False | False | Y | Y | Y | Y |
| Assembly detail | none | none | none | Y | Y | Y | Y |
| Assembly step count | 0 | 0 | 0 | Y | Y | Y | Y |
| HW design present | False | False | True | Y | **N** | **N** | **N** |
| HW design types | [] | [] | ['Electronic_Component'] | Y | **N** | **N** | **N** |
| HW editable src | False | False | True | Y | **N** | **N** | **N** |
| Mech design present | True | True | True | Y | Y | Y | Y |
| Mech design types | ['3D_Printable'] | ['3D_Printable'] | ['3D_Printable'] | Y | Y | Y | Y |
| Mech editable src | False | False | False | Y | Y | Y | Y |
| SW/FW present | True | True | True | Y | Y | Y | Y |
| SW/FW type | firmware | firmware | firmware | Y | Y | Y | Y |
| SW/FW frameworks | ['Teensy'] | ['Teensy'] | ['PJRC USB HID'] | Y | **N** | **N** | **N** |
| SW/FW doc level | referenced | basic | basic | **N** | **N** | Y | **N** |
| Testing present | True | True | True | Y | Y | Y | Y |
| Testing detail | basic | basic | basic | Y | Y | Y | Y |
| Cost mentioned | False | False | False | Y | Y | Y | Y |
| Suppliers ref'd | False | False | False | Y | Y | Y | Y |
| Part numbers | False | False | False | Y | Y | Y | Y |
| Maturity stage | unstated | unstated | unstated | Y | Y | Y | Y |
| HW license present | False | False | False | Y | Y | Y | Y |
| HW license name | None | None | None | Y | Y | Y | Y |
| SW license present | False | False | False | Y | Y | Y | Y |
| SW license name | None | None | None | Y | Y | Y | Y |
| Doc license present | False | False | False | Y | Y | Y | Y |
| Doc license name | None | None | None | Y | Y | Y | Y |

| **Totals** | | | | **35/36 (97%)** | **30/36 (83%)** | **31/36 (86%)** | **30/36 (83%)** |

---

## 4. VALKPC VF-1 (id=8662)

README: 1,052 chars | Tree: 7 entries

| Metric | Haiku | Gemini 3 | Flash Lite |
|--------|-------|----------|------------|
| Latency | 10.1s | 28.7s | 4.3s |
| Input tok | 6,633 | 6,422 | 6,422 |
| Output tok | 1,315 | 1,151 | 1,282 |
| JSON OK | Y | Y | Y |

| Field | Haiku | Gemini 3 | Flash Lite | H=G | H=FL | G=FL | All |
|-------|-------|----------|------------|-----|------|------|-----|
| Project type | hardware | hardware | hardware | Y | Y | Y | Y |
| Structure quality | well_structured | well_structured | well_structured | Y | Y | Y | Y |
| Doc location | inline | inline | inline | Y | Y | Y | Y |
| License present | True | True | True | Y | Y | Y | Y |
| License type | explicit | explicit | explicit | Y | Y | Y | Y |
| License name | CC BY-SA 4.0 International | CC BY-SA 4.0 International | CC BY-SA 4.0 International | Y | Y | Y | Y |
| Contributing present | False | False | False | Y | Y | Y | Y |
| Contributing level | 0 | 0 | 1 | Y | **N** | **N** | **N** |
| BOM present | True | True | True | Y | Y | Y | Y |
| BOM completeness | partial | partial | partial | Y | Y | Y | Y |
| BOM component count | 0 | 0 | 0 | Y | Y | Y | Y |
| Assembly present | False | True | True | **N** | **N** | Y | **N** |
| Assembly detail | none | referenced | referenced | **N** | **N** | Y | **N** |
| Assembly step count | 0 | 0 | 0 | Y | Y | Y | Y |
| HW design present | False | False | False | Y | Y | Y | Y |
| HW design types | [] | [] | [] | Y | Y | Y | Y |
| HW editable src | False | False | False | Y | Y | Y | Y |
| Mech design present | True | True | True | Y | Y | Y | Y |
| Mech design types | ['CAD'] | ['CAD'] | ['CAD'] | Y | Y | Y | Y |
| Mech editable src | True | True | True | Y | Y | Y | Y |
| SW/FW present | False | False | False | Y | Y | Y | Y |
| SW/FW type | none | none | none | Y | Y | Y | Y |
| SW/FW frameworks | [] | [] | [] | Y | Y | Y | Y |
| SW/FW doc level | none | none | none | Y | Y | Y | Y |
| Testing present | False | False | False | Y | Y | Y | Y |
| Testing detail | none | none | none | Y | Y | Y | Y |
| Cost mentioned | False | False | False | Y | Y | Y | Y |
| Suppliers ref'd | False | True | True | **N** | **N** | Y | **N** |
| Part numbers | False | False | False | Y | Y | Y | Y |
| Maturity stage | unstated | production | unstated | **N** | Y | **N** | **N** |
| HW license present | True | False | False | **N** | **N** | Y | **N** |
| HW license name | CC BY-SA 4.0 International | None | None | **N** | **N** | Y | **N** |
| SW license present | False | False | False | Y | Y | Y | Y |
| SW license name | None | None | None | Y | Y | Y | Y |
| Doc license present | True | True | True | Y | Y | Y | Y |
| Doc license name | CC BY-SA 4.0 International | CC BY-SA 4.0 International | CC BY-SA 4.0 International | Y | Y | Y | Y |

| **Totals** | | | | **30/36 (83%)** | **30/36 (83%)** | **34/36 (94%)** | **29/36 (81%)** |

---

## 5. Trixel LED (id=3037)

README: 757 chars | Tree: 277 entries

| Metric | Haiku | Gemini 3 | Flash Lite |
|--------|-------|----------|------------|
| Latency | 13.4s | 15.7s | 5.1s |
| Input tok | 9,541 | 9,538 | 9,538 |
| Output tok | 1,811 | 1,243 | 1,623 |
| JSON OK | Y | Y | Y |

| Field | Haiku | Gemini 3 | Flash Lite | H=G | H=FL | G=FL | All |
|-------|-------|----------|------------|-----|------|------|-----|
| Project type | hardware | mixed | hardware | **N** | Y | **N** | **N** |
| Structure quality | well_structured | well_structured | well_structured | Y | Y | Y | Y |
| Doc location | inline | inline | inline | Y | Y | Y | Y |
| License present | True | True | True | Y | Y | Y | Y |
| License type | explicit | explicit | explicit | Y | Y | Y | Y |
| License name | Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International | Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International | Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License | Y | **N** | **N** | **N** |
| Contributing present | False | False | False | Y | Y | Y | Y |
| Contributing level | 0 | 0 | 0 | Y | Y | Y | Y |
| BOM present | False | True | False | **N** | Y | **N** | **N** |
| BOM completeness | none | partial | none | **N** | Y | **N** | **N** |
| BOM component count | 0 | 0 | 0 | Y | Y | Y | Y |
| Assembly present | False | False | False | Y | Y | Y | Y |
| Assembly detail | none | none | none | Y | Y | Y | Y |
| Assembly step count | 0 | 0 | 0 | Y | Y | Y | Y |
| HW design present | True | True | True | Y | Y | Y | Y |
| HW design types | ['PCB_Layout', 'Circuit_Schematic'] | ['PCB_Layout', 'Circuit_Schematic'] | ['PCB_Layout', 'Circuit_Schematic'] | Y | Y | Y | Y |
| HW editable src | True | True | True | Y | Y | Y | Y |
| Mech design present | True | True | True | Y | Y | Y | Y |
| Mech design types | ['Technical_Drawing'] | ['Technical_Drawing'] | ['Technical_Drawing'] | Y | Y | Y | Y |
| Mech editable src | False | True | False | **N** | Y | **N** | **N** |
| SW/FW present | True | True | True | Y | Y | Y | Y |
| SW/FW type | firmware | firmware | firmware | Y | Y | Y | Y |
| SW/FW frameworks | ['Arduino'] | ['Arduino'] | ['Arduino'] | Y | Y | Y | Y |
| SW/FW doc level | basic | none | none | **N** | **N** | Y | **N** |
| Testing present | False | True | False | **N** | Y | **N** | **N** |
| Testing detail | none | none | none | Y | Y | Y | Y |
| Cost mentioned | False | False | False | Y | Y | Y | Y |
| Suppliers ref'd | False | False | False | Y | Y | Y | Y |
| Part numbers | False | False | False | Y | Y | Y | Y |
| Maturity stage | unstated | unstated | unstated | Y | Y | Y | Y |
| HW license present | False | False | False | Y | Y | Y | Y |
| HW license name | None | None | None | Y | Y | Y | Y |
| SW license present | False | False | False | Y | Y | Y | Y |
| SW license name | None | None | None | Y | Y | Y | Y |
| Doc license present | True | True | True | Y | Y | Y | Y |
| Doc license name | Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International | Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International | Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License | Y | **N** | **N** | **N** |

| **Totals** | | | | **30/36 (83%)** | **33/36 (92%)** | **29/36 (81%)** | **28/36 (78%)** |

---

## 6. Plessey GPD340: Reverse Engineering (id=2695)

README: 6,394 chars | Tree: 24 entries

| Metric | Haiku | Gemini 3 | Flash Lite |
|--------|-------|----------|------------|
| Latency | 12.9s | 48.0s | 7.2s |
| Input tok | 8,212 | 7,973 | 7,973 |
| Output tok | 1,521 | 326 | 2,550 |
| JSON OK | Y | N | N |

| Field | Haiku | Gemini 3 | Flash Lite | H=G | H=FL | G=FL | All |
|-------|-------|----------|------------|-----|------|------|-----|
| Project type | hardware | FAIL | FAIL | **N** | **N** | Y | **N** |
| Structure quality | well_structured | FAIL | FAIL | **N** | **N** | Y | **N** |
| Doc location | inline | FAIL | FAIL | **N** | **N** | Y | **N** |
| License present | True | FAIL | FAIL | **N** | **N** | Y | **N** |
| License type | referenced | FAIL | FAIL | **N** | **N** | Y | **N** |
| License name | None | FAIL | FAIL | **N** | **N** | Y | **N** |
| Contributing present | False | FAIL | FAIL | **N** | **N** | Y | **N** |
| Contributing level | 0 | FAIL | FAIL | **N** | **N** | Y | **N** |
| BOM present | False | FAIL | FAIL | **N** | **N** | Y | **N** |
| BOM completeness | none | FAIL | FAIL | **N** | **N** | Y | **N** |
| BOM component count | 0 | FAIL | FAIL | **N** | **N** | Y | **N** |
| Assembly present | False | FAIL | FAIL | **N** | **N** | Y | **N** |
| Assembly detail | none | FAIL | FAIL | **N** | **N** | Y | **N** |
| Assembly step count | 0 | FAIL | FAIL | **N** | **N** | Y | **N** |
| HW design present | True | FAIL | FAIL | **N** | **N** | Y | **N** |
| HW design types | ['Circuit_Schematic', 'PCB_Layout'] | FAIL | FAIL | **N** | **N** | Y | **N** |
| HW editable src | True | FAIL | FAIL | **N** | **N** | Y | **N** |
| Mech design present | False | FAIL | FAIL | **N** | **N** | Y | **N** |
| Mech design types | [] | FAIL | FAIL | **N** | **N** | Y | **N** |
| Mech editable src | False | FAIL | FAIL | **N** | **N** | Y | **N** |
| SW/FW present | True | FAIL | FAIL | **N** | **N** | Y | **N** |
| SW/FW type | firmware | FAIL | FAIL | **N** | **N** | Y | **N** |
| SW/FW frameworks | ['Pico SDK'] | FAIL | FAIL | **N** | **N** | Y | **N** |
| SW/FW doc level | basic | FAIL | FAIL | **N** | **N** | Y | **N** |
| Testing present | True | FAIL | FAIL | **N** | **N** | Y | **N** |
| Testing detail | detailed | FAIL | FAIL | **N** | **N** | Y | **N** |
| Cost mentioned | False | FAIL | FAIL | **N** | **N** | Y | **N** |
| Suppliers ref'd | False | FAIL | FAIL | **N** | **N** | Y | **N** |
| Part numbers | False | FAIL | FAIL | **N** | **N** | Y | **N** |
| Maturity stage | unstated | FAIL | FAIL | **N** | **N** | Y | **N** |
| HW license present | False | FAIL | FAIL | **N** | **N** | Y | **N** |
| HW license name | None | FAIL | FAIL | **N** | **N** | Y | **N** |
| SW license present | False | FAIL | FAIL | **N** | **N** | Y | **N** |
| SW license name | None | FAIL | FAIL | **N** | **N** | Y | **N** |
| Doc license present | False | FAIL | FAIL | **N** | **N** | Y | **N** |
| Doc license name | None | FAIL | FAIL | **N** | **N** | Y | **N** |

| **Totals** | | | | **0/36 (0%)** | **0/36 (0%)** | **36/36 (100%)** | **0/36 (0%)** |

---

## 7. X-Mas WTree (id=2473)

README: 3,556 chars | Tree: 56 entries

| Metric | Haiku | Gemini 3 | Flash Lite |
|--------|-------|----------|------------|
| Latency | 18.4s | 17.7s | 5.7s |
| Input tok | 7,821 | 7,576 | 7,576 |
| Output tok | 1,939 | 1,425 | 1,801 |
| JSON OK | Y | Y | N |

| Field | Haiku | Gemini 3 | Flash Lite | H=G | H=FL | G=FL | All |
|-------|-------|----------|------------|-----|------|------|-----|
| Project type | hardware | mixed | FAIL | **N** | **N** | **N** | **N** |
| Structure quality | basic | well_structured | FAIL | **N** | **N** | **N** | **N** |
| Doc location | inline | inline | FAIL | Y | **N** | **N** | **N** |
| License present | True | True | FAIL | Y | **N** | **N** | **N** |
| License type | referenced | file reference | FAIL | **N** | **N** | **N** | **N** |
| License name | None | None | FAIL | Y | **N** | **N** | **N** |
| Contributing present | False | False | FAIL | Y | **N** | **N** | **N** |
| Contributing level | 0 | 0 | FAIL | Y | **N** | **N** | **N** |
| BOM present | True | True | FAIL | Y | **N** | **N** | **N** |
| BOM completeness | partial | partial | FAIL | Y | **N** | **N** | **N** |
| BOM component count | 0 | 0 | FAIL | Y | **N** | **N** | **N** |
| Assembly present | True | True | FAIL | Y | **N** | **N** | **N** |
| Assembly detail | detailed | detailed | FAIL | Y | **N** | **N** | **N** |
| Assembly step count | 9 | 9 | FAIL | Y | **N** | **N** | **N** |
| HW design present | True | True | FAIL | Y | **N** | **N** | **N** |
| HW design types | ['PCB_Layout', 'Circuit_Schematic'] | ['PCB_Layout', 'Circuit_Schematic'] | FAIL | Y | **N** | **N** | **N** |
| HW editable src | True | True | FAIL | Y | **N** | **N** | **N** |
| Mech design present | True | True | FAIL | Y | **N** | **N** | **N** |
| Mech design types | ['CAD'] | ['CAD'] | FAIL | Y | **N** | **N** | **N** |
| Mech editable src | True | True | FAIL | Y | **N** | **N** | **N** |
| SW/FW present | True | True | FAIL | Y | **N** | **N** | **N** |
| SW/FW type | firmware | firmware | FAIL | Y | **N** | **N** | **N** |
| SW/FW frameworks | ['Arduino'] | ['WLED'] | FAIL | **N** | **N** | **N** | **N** |
| SW/FW doc level | referenced | referenced | FAIL | Y | **N** | **N** | **N** |
| Testing present | True | True | FAIL | Y | **N** | **N** | **N** |
| Testing detail | basic | basic | FAIL | Y | **N** | **N** | **N** |
| Cost mentioned | False | True | FAIL | **N** | **N** | **N** | **N** |
| Suppliers ref'd | True | True | FAIL | Y | **N** | **N** | **N** |
| Part numbers | True | True | FAIL | Y | **N** | **N** | **N** |
| Maturity stage | unstated | unstated | FAIL | Y | **N** | **N** | **N** |
| HW license present | False | False | FAIL | Y | **N** | **N** | **N** |
| HW license name | None | None | FAIL | Y | **N** | **N** | **N** |
| SW license present | False | False | FAIL | Y | **N** | **N** | **N** |
| SW license name | None | None | FAIL | Y | **N** | **N** | **N** |
| Doc license present | False | False | FAIL | Y | **N** | **N** | **N** |
| Doc license name | None | None | FAIL | Y | **N** | **N** | **N** |

| **Totals** | | | | **31/36 (86%)** | **0/36 (0%)** | **0/36 (0%)** | **0/36 (0%)** |

---

## 8. AYTABTU - Discrete Computer (id=1529)

README: 2,017 chars | Tree: 352 entries

| Metric | Haiku | Gemini 3 | Flash Lite |
|--------|-------|----------|------------|
| Latency | 12.9s | 21.0s | 5.0s |
| Input tok | 10,443 | 9,857 | 9,857 |
| Output tok | 1,509 | 1,222 | 1,714 |
| JSON OK | Y | Y | Y |

| Field | Haiku | Gemini 3 | Flash Lite | H=G | H=FL | G=FL | All |
|-------|-------|----------|------------|-----|------|------|-----|
| Project type | hardware | hardware | hardware | Y | Y | Y | Y |
| Structure quality | basic | well_structured | well_structured | **N** | **N** | Y | **N** |
| Doc location | inline | inline | inline | Y | Y | Y | Y |
| License present | True | True | True | Y | Y | Y | Y |
| License type | file reference | file reference | file reference | Y | Y | Y | Y |
| License name | None | None | None | Y | Y | Y | Y |
| Contributing present | False | False | False | Y | Y | Y | Y |
| Contributing level | 0 | 0 | 0 | Y | Y | Y | Y |
| BOM present | False | False | False | Y | Y | Y | Y |
| BOM completeness | none | none | none | Y | Y | Y | Y |
| BOM component count | 0 | 0 | 0 | Y | Y | Y | Y |
| Assembly present | False | False | False | Y | Y | Y | Y |
| Assembly detail | none | none | none | Y | Y | Y | Y |
| Assembly step count | 0 | 0 | 0 | Y | Y | Y | Y |
| HW design present | True | True | True | Y | Y | Y | Y |
| HW design types | ['PCB_Layout', 'Circuit_Schematic'] | ['PCB_Layout', 'Circuit_Schematic'] | ['PCB_Layout', 'Circuit_Schematic'] | Y | Y | Y | Y |
| HW editable src | True | True | True | Y | Y | Y | Y |
| Mech design present | False | False | True | Y | **N** | **N** | **N** |
| Mech design types | [] | [] | ['Other'] | Y | **N** | **N** | **N** |
| Mech editable src | False | False | False | Y | Y | Y | Y |
| SW/FW present | True | True | True | Y | Y | Y | Y |
| SW/FW type | firmware | firmware | firmware | Y | Y | Y | Y |
| SW/FW frameworks | ['Arduino'] | ['Arduino'] | ['Arduino'] | Y | Y | Y | Y |
| SW/FW doc level | basic | basic | none | Y | **N** | **N** | **N** |
| Testing present | True | True | True | Y | Y | Y | Y |
| Testing detail | basic | basic | basic | Y | Y | Y | Y |
| Cost mentioned | False | False | False | Y | Y | Y | Y |
| Suppliers ref'd | False | False | False | Y | Y | Y | Y |
| Part numbers | False | False | False | Y | Y | Y | Y |
| Maturity stage | unstated | unstated | prototype | Y | **N** | **N** | **N** |
| HW license present | False | False | False | Y | Y | Y | Y |
| HW license name | None | None | None | Y | Y | Y | Y |
| SW license present | False | False | False | Y | Y | Y | Y |
| SW license name | None | None | None | Y | Y | Y | Y |
| Doc license present | False | False | False | Y | Y | Y | Y |
| Doc license name | None | None | None | Y | Y | Y | Y |

| **Totals** | | | | **35/36 (97%)** | **31/36 (86%)** | **32/36 (89%)** | **31/36 (86%)** |

---

## 9. Tsunami Super WAV Trigger (id=8605)

README: 2,318 chars | Tree: 23 entries

| Metric | Haiku | Gemini 3 | Flash Lite |
|--------|-------|----------|------------|
| Latency | 10.7s | 41.7s | 4.7s |
| Input tok | 7,194 | 6,929 | 6,929 |
| Output tok | 1,244 | 326 | 1,432 |
| JSON OK | Y | N | Y |

| Field | Haiku | Gemini 3 | Flash Lite | H=G | H=FL | G=FL | All |
|-------|-------|----------|------------|-----|------|------|-----|
| Project type | hardware | FAIL | hardware | **N** | Y | **N** | **N** |
| Structure quality | well_structured | FAIL | well_structured | **N** | Y | **N** | **N** |
| Doc location | external_repo | FAIL | inline | **N** | **N** | **N** | **N** |
| License present | True | FAIL | True | **N** | Y | **N** | **N** |
| License type | referenced | FAIL | referenced | **N** | Y | **N** | **N** |
| License name | None | FAIL | None | **N** | Y | **N** | **N** |
| Contributing present | False | FAIL | False | **N** | Y | **N** | **N** |
| Contributing level | 0 | FAIL | 0 | **N** | Y | **N** | **N** |
| BOM present | False | FAIL | False | **N** | Y | **N** | **N** |
| BOM completeness | none | FAIL | none | **N** | Y | **N** | **N** |
| BOM component count | 0 | FAIL | 0 | **N** | Y | **N** | **N** |
| Assembly present | False | FAIL | True | **N** | **N** | **N** | **N** |
| Assembly detail | none | FAIL | referenced | **N** | **N** | **N** | **N** |
| Assembly step count | 0 | FAIL | 0 | **N** | Y | **N** | **N** |
| HW design present | True | FAIL | True | **N** | Y | **N** | **N** |
| HW design types | ['PCB_Layout', 'Circuit_Schematic'] | FAIL | ['PCB_Layout', 'Circuit_Schematic'] | **N** | Y | **N** | **N** |
| HW editable src | True | FAIL | True | **N** | Y | **N** | **N** |
| Mech design present | False | FAIL | False | **N** | Y | **N** | **N** |
| Mech design types | [] | FAIL | [] | **N** | Y | **N** | **N** |
| Mech editable src | False | FAIL | False | **N** | Y | **N** | **N** |
| SW/FW present | False | FAIL | True | **N** | **N** | **N** | **N** |
| SW/FW type | none | FAIL | firmware | **N** | **N** | **N** | **N** |
| SW/FW frameworks | [] | FAIL | [] | **N** | Y | **N** | **N** |
| SW/FW doc level | none | FAIL | referenced | **N** | **N** | **N** | **N** |
| Testing present | False | FAIL | False | **N** | Y | **N** | **N** |
| Testing detail | none | FAIL | none | **N** | Y | **N** | **N** |
| Cost mentioned | False | FAIL | False | **N** | Y | **N** | **N** |
| Suppliers ref'd | False | FAIL | False | **N** | Y | **N** | **N** |
| Part numbers | False | FAIL | False | **N** | Y | **N** | **N** |
| Maturity stage | production | FAIL | production | **N** | Y | **N** | **N** |
| HW license present | False | FAIL | True | **N** | **N** | **N** | **N** |
| HW license name | None | FAIL | None | **N** | Y | **N** | **N** |
| SW license present | False | FAIL | False | **N** | Y | **N** | **N** |
| SW license name | None | FAIL | None | **N** | Y | **N** | **N** |
| Doc license present | False | FAIL | False | **N** | Y | **N** | **N** |
| Doc license name | None | FAIL | None | **N** | Y | **N** | **N** |

| **Totals** | | | | **0/36 (0%)** | **29/36 (81%)** | **0/36 (0%)** | **0/36 (0%)** |

---

## 10. Arduino  FM radio (id=1146)

README: 3,854 chars | Tree: 17 entries

| Metric | Haiku | Gemini 3 | Flash Lite |
|--------|-------|----------|------------|
| Latency | 17.8s | 21.7s | 6.5s |
| Input tok | 7,594 | 7,268 | 7,268 |
| Output tok | 2,173 | 1,922 | 2,071 |
| JSON OK | Y | Y | Y |

| Field | Haiku | Gemini 3 | Flash Lite | H=G | H=FL | G=FL | All |
|-------|-------|----------|------------|-----|------|------|-----|
| Project type | hardware | mixed | hardware | **N** | Y | **N** | **N** |
| Structure quality | basic | well_structured | well_structured | **N** | **N** | Y | **N** |
| Doc location | inline | inline | inline | Y | Y | Y | Y |
| License present | True | True | False | Y | **N** | **N** | **N** |
| License type | referenced | file reference | none | **N** | **N** | **N** | **N** |
| License name | None | None | None | Y | Y | Y | Y |
| Contributing present | False | False | False | Y | Y | Y | Y |
| Contributing level | 0 | 0 | 0 | Y | Y | Y | Y |
| BOM present | True | True | True | Y | Y | Y | Y |
| BOM completeness | basic | basic | basic | Y | Y | Y | Y |
| BOM component count | 12 | 10 | 0 | **N** | **N** | **N** | **N** |
| Assembly present | False | False | False | Y | Y | Y | Y |
| Assembly detail | none | none | none | Y | Y | Y | Y |
| Assembly step count | 0 | 0 | 0 | Y | Y | Y | Y |
| HW design present | True | True | True | Y | Y | Y | Y |
| HW design types | ['Circuit_Schematic'] | ['Circuit_Schematic'] | ['Circuit_Schematic'] | Y | Y | Y | Y |
| HW editable src | True | True | True | Y | Y | Y | Y |
| Mech design present | False | False | False | Y | Y | Y | Y |
| Mech design types | [] | [] | [] | Y | Y | Y | Y |
| Mech editable src | False | False | False | Y | Y | Y | Y |
| SW/FW present | True | True | True | Y | Y | Y | Y |
| SW/FW type | firmware | firmware | firmware | Y | Y | Y | Y |
| SW/FW frameworks | ['Arduino'] | ['Arduino'] | ['Arduino'] | Y | Y | Y | Y |
| SW/FW doc level | basic | basic | basic | Y | Y | Y | Y |
| Testing present | True | False | True | **N** | Y | **N** | **N** |
| Testing detail | basic | none | basic | **N** | Y | **N** | **N** |
| Cost mentioned | False | False | False | Y | Y | Y | Y |
| Suppliers ref'd | True | True | True | Y | Y | Y | Y |
| Part numbers | False | False | False | Y | Y | Y | Y |
| Maturity stage | unstated | unstated | unstated | Y | Y | Y | Y |
| HW license present | False | False | False | Y | Y | Y | Y |
| HW license name | None | None | None | Y | Y | Y | Y |
| SW license present | False | False | False | Y | Y | Y | Y |
| SW license name | None | None | None | Y | Y | Y | Y |
| Doc license present | False | False | False | Y | Y | Y | Y |
| Doc license name | None | None | None | Y | Y | Y | Y |

| **Totals** | | | | **30/36 (83%)** | **32/36 (89%)** | **30/36 (83%)** | **29/36 (81%)** |

---

## Aggregate Agreement

| Pair | Matches | Total | Agreement |
|------|---------|-------|-----------|
| Haiku vs Gemini 3 | 256 | 360 | 71.1% |
| Haiku vs Flash Lite | 249 | 360 | 69.2% |
| Gemini 3 vs Flash Lite | 257 | 360 | 71.4% |
| All three agree | 209 | 360 | 58.1% |

## Cost Summary

| Model | Input tok | Output tok | Cost | Per-project | Extrap (7,057) |
|-------|-----------|------------|------|-------------|----------------|
| Haiku 4.5 | 83,778 | 17,416 | $0.1709 | $0.0171 | $120.57 |
| Gemini 3 Flash | 81,205 | 11,735 | $0.0758 | $0.0076 | $53.50 |
| Flash Lite | 81,205 | 17,553 | $0.0076 | $0.0008 | $5.34 |
