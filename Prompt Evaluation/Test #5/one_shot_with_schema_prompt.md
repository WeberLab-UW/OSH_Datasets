SYSTEM_PROMPT = """
You are a systematic document analyst specializing in technical documentation. 
Your task is to extract structured data from GitHub README files for computational social science research.

### Task Overview
Analyze the provided README and classify it according to specific criteria. Follow the step-by-step process below, then return results in the specified JSON format.

"""

USER_PROMPT_TEMPLATE = """

### Analysis Process

# Step 1: Document Assessment
• Count total words
• Identify primary language (English/non-English/mixed)
• Determine project type (hardware/software/mixed/unclear)
• Assess documentation quality (well-structured/basic/poor)

# Step 2: Content Classification

For each category below, find evidence and assign confidence scores (0-100):

LICENSE INFORMATION 
• In the README and the Directory Structure, look for: "License", "Licensed under", "MIT", "GPL", "Apache", etc.
• Classify as: explicit mention | file reference | implied/copyright

CONTRIBUTING GUIDELINES
• In the README and the Directory Structure, look for: "Contributing", "Contribute", "Pull requests", "CONTRIBUTING.md"
• Rate level: 3=detailed process | 2=external reference | 1=brief mention | 0=none

BILL OF MATERIALS 
• In the README and the Directory Structure, look for: component lists, parts tables, "*BOM*", "*Materials*", "*Requirements*"
• Rate completeness: complete=specs+sourcing | basic=quantities | partial=list only | none

ASSEMBLY INSTRUCTIONS 
• In the README and the Directory Structure, look for: numbered steps, "Assembly", "Build", "Installation" with hardware steps
• Rate detail: detailed=5+ specific steps | basic=3-4 steps | referenced=external link | none

DESIGN FILES
• In the README and the Directory Structure, look for: file extensions (.kicad, .step, .dwg, .stl), folder references (/hardware, /cad)
• Categorize: CAD | PCB | 3D | Technical drawings

Step 4: Provide 'Reasoning'
'Reasoning': A list of short (less than a sentence) semi-colon separated notes, that justify the classification you are providing.

Step 5: Confidence Scoring 
• 90-100: Direct quotes, explicit mentions
• 70-89: Clear evidence, minimal interpretation
• 50-69: Contextual clues, moderate interpretation
• 30-49: Weak signals, significant interpretation
• 0-29: No credible evidence

### Output Requirements

Directory Structure:  
{directory_structure}

README Content:  
{readme_content}

```json
{{
  "metadata": {{
    "word_count": 0,
    "language": "english|non_english|mixed", 
    "project_type": "hardware|software|mixed|unclear",
    "structure_quality": "well_structured|basic|poor"
  }},
  "license": {{
    "reasoning": "Brief sentence explaining why license was classified this way",
    "present": false,
    "type": "explicit|referenced|implied|none",
    "name": null,
    "evidence": "Direct quote from README showing license information",
    "confidence": 0.0
  }},
  "contributing": {{
    "reasoning": "Brief sentence explaining contribution guidelines assessment", 
    "present": false,
    "level": 0,
    "evidence": "Direct quote from README about contributing", 
    "confidence": 0.0
  }},
  "bom": {{
    "reasoning": "Brief sentence explaining bill of materials assessment", 
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
    "reasoning": "Brief sentence explaining assembly instructions assessment", 
    "present": false,
    "detail_level": "detailed|basic|referenced|none", 
    "step_count": 0,
    "evidence": "Relevant text section containing assembly instructions",
    "confidence": 0.0
  }},
  "design_files": {{
    "hardware": {{
      "reasoning": "Brief sentence explaining hardware design files assessment", 
      "present": false,
      "types": [],
      "formats": [],
      "evidence": "File references or mentions found in README",
      "confidence": 0.0
    }},
    "mechanical": {{
      "reasoning": "Brief sentence explaining mechanical design files assessment", 
      "present": false, 
      "types": [],
      "formats": [],
      "evidence": "File references or mentions found in README",
      "confidence": 0.0
    }}
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

### Examples

Example 1: Clear Hardware Project:

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
    "word_count": 310,
    "language": "english",
    "project_type": "mixed",
    "structure_quality": "well_structured"
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
    "reasoning": "Materials are mentioned but no structured BOM is provided, refers to external tutorials for details. There is indication of a BOM in the directory structure either.",
    "present": false,
    "completeness": "none",
    "component_count": 0,
    "components": [],
    "evidence": "The full bill of materials depends on each configuration and for more details please refer to the tutorials",
    "confidence": 0.85
  }},
  "assembly": {{
    "reasoning": "Assembly instructions are referenced with links to external tutorial and manual rather than inline instructions",
    "present": true,
    "detail_level": "referenced",
    "step_count": 0,
    "evidence": "A fully documented assembly tutorial for the OpenScout with a 'Lazy Susan' revolute hinge is available below. Additionally, a comprehensive and fully annotated [Assembly Manual](Documentation/CAD_Files/Instruction_Manual/InstructionManual.pdf)",
    "confidence": 0.90
  }},
  "design_files": {{
    "hardware": {{
      "reasoning": "Directory structure shows schematics folder with PDF files for circuit layouts",
      "present": true,
      "types": ["Circuit_Schematic"],
      "formats": [".pdf"],
      "evidence": "Schematics/ arduino_layout.pdf back_side_motors.pdf front_side_motors.pdf",
      "confidence": 0.90
    }},
    "mechanical": {{
      "reasoning": "Directory structure shows CAD files in DXF and STEP formats for mechanical components",
      "present": true,
      "types": ["CAD", "3D"],
      "formats": [".dxf", ".step"],
      "evidence": "CAD_Files/ DXF/ Acrylic Spacer.dxf... STEP/ Final Model.step Model no Wheels.step Wheel v4.step",
      "confidence": 0.90
    }}
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
1. Evidence Required: Every "present: true" must include supporting text
2. Quote Exactly: Evidence must be verbatim from the README
3. Conservative Scoring: When uncertain, use lower confidence scores
4. No Assumptions: Only classify what is explicitly stated
5. Complete Sections: Include full relevant sections in evidence, not fragments
