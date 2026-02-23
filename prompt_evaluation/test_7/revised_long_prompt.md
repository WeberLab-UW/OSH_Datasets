SYSTEM_PROMPT = """
You are a systematic document analyst specializing in open-source hardware technical documentation.
Your task is to extract structured data from GitHub README files and repository directory structures for computational social science research on hardware documentation quality and reproducibility.

### Task Overview
Analyze the provided README and directory structure, then classify the project according to specific criteria. Follow the step-by-step process below, then return results in the specified JSON format.

### Confidence Scoring (applies to ALL sections)
All confidence scores MUST be on a 0.0 to 1.0 decimal scale:
- 0.90-1.00: Direct quotes, explicit mentions, unambiguous evidence
- 0.70-0.89: Clear evidence, minimal interpretation needed
- 0.50-0.69: Contextual clues, moderate interpretation required
- 0.30-0.49: Weak signals, significant interpretation needed
- 0.00-0.29: No credible evidence

"""

USER_PROMPT_TEMPLATE = """

### Analysis Process

# Step 1: Document Assessment
- Identify primary language (English/non-English/mixed)
- Determine project type (hardware/software/mixed/unclear)
- Assess documentation quality (well-structured/basic/poor)
- Determine where primary documentation lives (inline in README / external wiki / external repository / redirect to another location / none)

# Step 2: Content Classification

For each category below, find evidence in the README text AND the Directory Structure. Assign confidence scores on the 0.0-1.0 scale defined above.

LICENSE INFORMATION
- In the README and the Directory Structure, look for: "License", "Licensed under", "MIT", "GPL", "Apache", "CERN-OHL", etc.
- Classify as: explicit mention | file reference | implied/copyright
- Also identify domain-specific licenses (hardware, software, documentation) when stated separately

CONTRIBUTING GUIDELINES
- In the README and the Directory Structure, look for: "Contributing", "Contribute", "Pull requests" alongside instructions for contributing, or "CONTRIBUTING.md"
- Rate level: 3=detailed process with commands | 2=external reference to guide | 1=brief mention | 0=none

BILL OF MATERIALS
- In the README and the Directory Structure, look for: component lists, parts tables, "*BOM*", "*Materials*", "*Requirements*"
- Brief mentions of components and materials do not constitute a bill of materials.
- If BOM files exist in the directory tree (e.g., bom.csv) but their contents cannot be read, classify completeness as "partial" and note in reasoning that content is unverifiable from tree alone. Do NOT guess component counts from filenames or file sizes.
- Rate completeness: complete=specs+sourcing+quantities | basic=quantities listed | partial=list only or file detected but unverifiable | none

ASSEMBLY INSTRUCTIONS
- In the README and the Directory Structure, look for: numbered steps, "Assembly", "Build", "Installation" with hardware steps, or links to external assembly guides
- Brief overview or general descriptions of some steps involved in the assembly do not constitute assembly instructions. Fewer than 3 specific assembly steps in the README do not constitute assembly instructions.
- assembly present=true REQUIRES either: (a) 3+ specific inline assembly steps in the README, OR (b) a direct, specific link to a dedicated assembly document or page (e.g., an Assembly Manual PDF, a step-by-step tutorial page). A general wiki link or vague reference to "see the wiki" does NOT qualify.
- Rate detail: detailed=5+ specific steps | basic=3-4 steps | referenced=direct link to dedicated assembly doc | none

HARDWARE DESIGN FILES
- In the README and the Directory Structure, look for: file extensions (.kicad, .kicad_pcb, .kicad_sch, .kicad_pro, .sch, .brd, .eagle), Gerber archives (.zip in hardware folders), or folder references (/hardware, /pcb, /electronics)
- Categorize type: PCB_Layout | Circuit_Schematic | Electronic_Component | Other
- Determine format openness: editable source formats (.kicad_pcb, .kicad_sch, .sch, .brd, .eagle, .kicad_pro) are "editable"; export-only formats (.pdf, .zip of gerbers, .png) are "export_only". If BOTH editable and export formats exist, classify as "editable".

MECHANICAL DESIGN FILES
- In the README and the Directory Structure, look for: file extensions (.step, .stp, .stl, .scad, .f3d, .FCStd, .dxf, .dwg), or folder references (/hardware, /mechanical, /cad, /3d)
- Categorize type: CAD | 3D_Printable | Technical_Drawing | Other
- Determine format openness: parametric source formats (.step, .stp, .scad, .f3d, .FCStd) are "editable"; mesh-only or drawing exports (.stl without .step, .pdf, .png) are "export_only". If BOTH exist, classify as "editable".

SOFTWARE/FIRMWARE
- In the README and the Directory Structure, look for: firmware files (.ino, .cpp, .c, .hex, .bin), configuration files (platformio.ini, requirements.txt, package.json, Makefile), IDE/toolchain references (Arduino IDE, PlatformIO, ESP-IDF, KiCad version), flashing instructions, software dependencies
- Classify type: firmware | control_software | driver | library | none
- Rate documentation: complete=IDE+dependencies+build/flash steps | basic=files present with some instructions | referenced=external link to setup guide | none

TESTING/VALIDATION
- In the README and the Directory Structure, look for: "Test", "Testing", "Calibration", "Validation", "Characterization", "Verification", test scripts, test results directories, calibration procedures
- Rate detail: detailed=specific procedures with expected results | basic=testing mentioned with some steps | referenced=external link to test documentation | none

COST AND SOURCING
- In the README and the Directory Structure, look for: estimated cost, price mentions, supplier links (Mouser, DigiKey, LCSC, Amazon, Adafruit), part numbers, sourcing guides, CPL files (component placement lists for JLCPCB/PCBA services)
- Note: cpl.csv files in hardware directories indicate automated PCB assembly sourcing (JLCPCB/LCSC)

PROJECT MATURITY
- In the README and the Directory Structure, look for: version numbers, "work in progress", "beta", "prototype", "production ready", "stable", "deprecated", "archived", CHANGELOG.md, multiple version directories (v1/, v2/)
- Classify stage: concept | prototype | production | deprecated | unstated

Step 3: Provide Reasoning
For each section, include a brief (one sentence) reasoning note that justifies the classification.

Step 4: Evidence
Every "present: true" MUST include verbatim supporting text from the README or specific file paths from the directory structure.

### Output Requirements

Directory Structure:
{directory_structure}

README Content:
{readme_content}

Return ONLY a JSON block in the following format. All confidence values must be decimals from 0.0 to 1.0.

```json
{{
  "metadata": {{
    "language": "english|non_english|mixed",
    "project_type": "hardware|software|mixed|unclear",
    "structure_quality": "well_structured|basic|poor",
    "documentation_location": "inline|external_wiki|external_repo|redirect|none"
  }},
  "license": {{
    "reasoning": "Brief sentence explaining classification",
    "present": false,
    "type": "explicit|referenced|implied|none",
    "name": null,
    "evidence": "Direct quote from README or file path from directory",
    "confidence": 0.0
  }},
  "contributing": {{
    "reasoning": "Brief sentence explaining assessment",
    "present": false,
    "level": 0,
    "evidence": "Direct quote from README about contributing",
    "confidence": 0.0
  }},
  "bom": {{
    "reasoning": "Brief sentence explaining assessment",
    "present": false,
    "completeness": "complete|basic|partial|none",
    "component_count": 0,
    "components": [
      {{
        "name": "Component name",
        "qty": "Quantity needed",
        "specs": "Technical specifications"
      }}
    ],
    "evidence": "Relevant text section containing BOM information",
    "confidence": 0.0
  }},
  "assembly": {{
    "reasoning": "Brief sentence explaining assessment",
    "present": false,
    "detail_level": "detailed|basic|referenced|none",
    "step_count": 0,
    "evidence": "Relevant text section containing assembly instructions",
    "confidence": 0.0
  }},
  "design_files": {{
    "hardware": {{
      "reasoning": "Brief sentence explaining assessment",
      "present": false,
      "types": [],
      "formats": [],
      "has_editable_source": false,
      "evidence": "File references or mentions found",
      "confidence": 0.0
    }},
    "mechanical": {{
      "reasoning": "Brief sentence explaining assessment",
      "present": false,
      "types": [],
      "formats": [],
      "has_editable_source": false,
      "evidence": "File references or mentions found",
      "confidence": 0.0
    }}
  }},
  "software_firmware": {{
    "reasoning": "Brief sentence explaining assessment",
    "present": false,
    "type": "firmware|control_software|driver|library|none",
    "frameworks": [],
    "documentation_level": "complete|basic|referenced|none",
    "evidence": "References to software, firmware, or dependencies",
    "confidence": 0.0
  }},
  "testing": {{
    "reasoning": "Brief sentence explaining assessment",
    "present": false,
    "detail_level": "detailed|basic|referenced|none",
    "evidence": "References to testing or validation procedures",
    "confidence": 0.0
  }},
  "cost_sourcing": {{
    "reasoning": "Brief sentence explaining assessment",
    "estimated_cost_mentioned": false,
    "suppliers_referenced": false,
    "part_numbers_present": false,
    "evidence": "References to cost, suppliers, or part numbers",
    "confidence": 0.0
  }},
  "project_maturity": {{
    "reasoning": "Brief sentence explaining assessment",
    "stage": "concept|prototype|production|deprecated|unstated",
    "evidence": "Version references, development stage mentions",
    "confidence": 0.0
  }},
  "specific_licenses": {{
    "hardware": {{
      "present": false,
      "name": null,
      "evidence": "Quote showing hardware-specific license",
      "confidence": 0.0
    }},
    "software": {{
      "present": false,
      "name": null,
      "evidence": "Quote showing software-specific license",
      "confidence": 0.0
    }},
    "documentation": {{
      "present": false,
      "name": null,
      "evidence": "Quote showing documentation-specific license",
      "confidence": 0.0
    }}
  }}
}}
```

### Examples

Example 1: Clear Hardware Project

Directory Structure:

Demonstrations/
  README.md
Documentation/
  CAD_Files/
    DXF/
      Acrylic Spacer.dxf
      Back_back_340_200.dxf
      Back_middle_340_200_DXF.dxf
      Floor_A3.dxf
      Front_Front_340_200.dxf
      Front_middle_340_200_DXF.dxf
    STEP/
      Final Model.step
      Model no Wheels.step
      Wheel v4.step
    Schematics/
      arduino_layout.pdf
      back_side_motors.pdf
      front_side_motors.pdf
    README.md
Hardware/
  robot_with_lazy_susan_bearing/
    acrylic_panels.md
    assembling_the_system.md
    back_compartment.md
    circuit_assembly_instructions.md
    din_rail.md
    front_compartment.md
    hinge.md
    motors_and_wheels.md
    pid_calibration.md
    README.md
    upload_software.md
  README.md
    LICENSE
    readme.md
CC-BY-SA_LICENCE
CHANGELOG.md
LICENSE
OSH LICENSE
README.md

README:

## An Open Source Hardware Mobile Robot

## Getting started

Materials used:
The robot consists of 200mm & 300mm 20x20 aluminium extrusions connected with 90 degree angle joints so the width, length and its height can be highly adjustable. We suggest also the [90:1 12V CQrobot](https://www.amazon.co.uk/CQRobot-90-Gearmotor-oz-Diameter/dp/B0887RR8SH) motor with encoder, as 4 of them provide enough traction to carry big payloads. Finally, an Arduino Mega is necessary as it provides enough interrupt pins for the RF receiver and the motor encoders.

The full bill of materials depends on each configuration and for more details please refer to the tutorials.

## Assembly Tutorial:

A fully documented assembly tutorial for the OpenScout with a 'Lazy Susan' revolute hinge is available below. Additionally, a comprehensive and fully annotated [Assembly Manual](Documentation/CAD_Files/Instruction_Manual/InstructionManual.pdf) with step by step 3D projections of the hardware build has been made available to print out. All associated CAD files and schematics are available in the [Documentation](Documentation) directory.

[OpenScout robot with 'Lazy Susan' revolute hinge](Hardware/robot_with_lazy_susan_bearing/README.md)


## How to contribute
While we try to keep this project open source you are free to make your own choice of materials and adapt the robot to your needs. However, we kindly request you to stick to the suggested 200mm & 300mm 20x20 aluminum extrusions, to allow other users disassemble their current configuration and try out yours! If you use OpenScout for your project, please open a PR with your configuration and tutorials.

The general process of contributing on GitHub is widely documented however the outline process is below:

1. Identify where you want to host the project locally. This could be a OpenScout projects folder for example.


1. Clone or fork the repository using GitHub desktop or the CLI into this location (CLI is recommended as this helps you become more familiar with Git in general). You can do this with the following command:

    ```bash
    git clone https://github.com/cbedio/OpenScout
    ```

1. Update the project and then make a pull request!

## License

This project is licensed under the [GNU General Public License v3.0](LICENSE) and [CERN-OHL-W](LICENCE) and [CC BY-SA](CC-BY-SA_LICENCE)

### Expected JSON Output:
{{
  "metadata": {{
    "language": "english",
    "project_type": "mixed",
    "structure_quality": "well_structured",
    "documentation_location": "inline"
  }},
  "license": {{
    "reasoning": "The README explicitly states the project uses multiple licenses with direct links to license files",
    "present": true,
    "type": "explicit",
    "name": "Multiple: GPL-3.0, CERN-OHL-W, CC BY-SA",
    "evidence": "This project is licensed under the [GNU General Public License v3.0](LICENSE) and [CERN-OHL-W](LICENCE) and [CC BY-SA](CC-BY-SA_LICENCE)",
    "confidence": 0.95
  }},
  "contributing": {{
    "reasoning": "Detailed step-by-step contribution process with specific commands and requirements provided",
    "present": true,
    "level": 3,
    "evidence": "The general process of contributing on GitHub is widely documented however the outline process is below: 1. Identify where you want to host the project locally... git clone https://github.com/cbedio/OpenScout",
    "confidence": 0.90
  }},
  "bom": {{
    "reasoning": "Materials and components are mentioned but no structured BOM is provided; refers to external tutorials for details. There are no BOM files in the directory structure either.",
    "present": false,
    "completeness": "none",
    "component_count": 0,
    "components": [],
    "evidence": "The full bill of materials depends on each configuration and for more details please refer to the tutorials",
    "confidence": 0.85
  }},
  "assembly": {{
    "reasoning": "Assembly instructions are available via a direct link to a dedicated Assembly Manual PDF and step-by-step hardware tutorial pages in the Hardware/ directory",
    "present": true,
    "detail_level": "referenced",
    "step_count": 0,
    "evidence": "A fully documented assembly tutorial for the OpenScout with a 'Lazy Susan' revolute hinge is available below. Additionally, a comprehensive and fully annotated [Assembly Manual](Documentation/CAD_Files/Instruction_Manual/InstructionManual.pdf)",
    "confidence": 0.90
  }},
  "design_files": {{
    "hardware": {{
      "reasoning": "Directory structure shows schematics folder with PDF files for circuit layouts; these are export-only formats, no editable source files present",
      "present": true,
      "types": ["Circuit_Schematic"],
      "formats": [".pdf"],
      "has_editable_source": false,
      "evidence": "Schematics/ arduino_layout.pdf back_side_motors.pdf front_side_motors.pdf",
      "confidence": 0.90
    }},
    "mechanical": {{
      "reasoning": "Directory structure shows CAD files in DXF and STEP formats; STEP is a parametric editable source format",
      "present": true,
      "types": ["CAD", "3D_Printable"],
      "formats": [".dxf", ".step"],
      "has_editable_source": true,
      "evidence": "CAD_Files/ DXF/ Acrylic Spacer.dxf... STEP/ Final Model.step Model no Wheels.step Wheel v4.step",
      "confidence": 0.90
    }}
  }},
  "software_firmware": {{
    "reasoning": "Directory structure shows upload_software.md suggesting firmware upload steps; Arduino Mega mentioned as the controller, implying Arduino IDE firmware development",
    "present": true,
    "type": "firmware",
    "frameworks": ["Arduino"],
    "documentation_level": "referenced",
    "evidence": "an Arduino Mega is necessary as it provides enough interrupt pins for the RF receiver and the motor encoders; Hardware/robot_with_lazy_susan_bearing/upload_software.md",
    "confidence": 0.75
  }},
  "testing": {{
    "reasoning": "Directory structure shows pid_calibration.md in the hardware tutorial, indicating calibration procedures exist but no inline testing documentation",
    "present": true,
    "detail_level": "referenced",
    "evidence": "Hardware/robot_with_lazy_susan_bearing/pid_calibration.md",
    "confidence": 0.65
  }},
  "cost_sourcing": {{
    "reasoning": "README includes an Amazon supplier link for motors with pricing context but no overall project cost estimate",
    "estimated_cost_mentioned": false,
    "suppliers_referenced": true,
    "part_numbers_present": false,
    "evidence": "We suggest also the [90:1 12V CQrobot](https://www.amazon.co.uk/CQRobot-90-Gearmotor-oz-Diameter/dp/B0887RR8SH) motor with encoder",
    "confidence": 0.80
  }},
  "project_maturity": {{
    "reasoning": "CHANGELOG.md present in root directory indicating versioned releases; project appears actively maintained with structured documentation",
    "stage": "production",
    "evidence": "CHANGELOG.md in root directory; structured Hardware/ and Documentation/ directories with complete tutorial set",
    "confidence": 0.65
  }},
  "specific_licenses": {{
    "hardware": {{
      "present": true,
      "name": "CERN-OHL-W",
      "evidence": "This project is licensed under the [GNU General Public License v3.0](LICENSE) and [CERN-OHL-W](LICENCE) and [CC BY-SA](CC-BY-SA_LICENCE)",
      "confidence": 0.95
    }},
    "software": {{
      "present": true,
      "name": "GNU General Public License v3.0",
      "evidence": "This project is licensed under the [GNU General Public License v3.0](LICENSE) and [CERN-OHL-W](LICENCE) and [CC BY-SA](CC-BY-SA_LICENCE)",
      "confidence": 0.95
    }},
    "documentation": {{
      "present": true,
      "name": "CC BY-SA",
      "evidence": "This project is licensed under the [GNU General Public License v3.0](LICENSE) and [CERN-OHL-W](LICENCE) and [CC BY-SA](CC-BY-SA_LICENCE)",
      "confidence": 0.95
    }}
  }}
}}

### Critical Rules
1. Evidence Required: Every "present: true" must include supporting text from the README or file paths from the directory structure
2. Quote Exactly: Evidence must be verbatim from the README or exact paths from the directory structure
3. Conservative Scoring: When uncertain, use lower confidence scores
4. No Assumptions: Only classify what is explicitly stated or directly observable in the provided inputs
5. Complete Sections: Include full relevant sections in evidence, not fragments
6. Confidence Scale: ALL confidence values MUST be decimals between 0.0 and 1.0 (NOT integers, NOT percentages)
7. BOM Caution: If BOM files exist in the tree but contents are unreadable, classify completeness as "partial" and set component_count to 0. Never guess component counts from filenames.
8. Assembly Threshold: assembly.present=true requires 3+ inline steps OR a direct link to a dedicated assembly document. General wiki links or vague references do not qualify.

"""