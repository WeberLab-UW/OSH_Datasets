# Research-Grade GitHub README Analysis Prompt

Analyze this README file and extract structured information following rigorous classification criteria. Return your response as valid JSON following the exact schema below.

## Operational Definitions

### License Information
- **Explicit**: Direct statement of license (e.g., "Licensed under MIT", "GPL v3")
- **Referenced**: Points to license file/section (e.g., "see LICENSE file")  
- **Implied**: Copyright notice or terms without specific license name

### Contributing Guidelines
- **Level 3**: Detailed guidelines with process, standards, code of conduct
- **Level 2**: Reference to external CONTRIBUTING file or section
- **Level 1**: Brief mention of contribution process (<50 words)
- **Level 0**: No contribution information

### Bill of Materials
- **Complete**: Table/list with quantities, specifications, and sourcing info
- **Basic**: List with quantities but minimal specifications
- **Partial**: Component list without quantities or incomplete
- **None**: No component information

### Assembly Instructions  
- **Detailed**: Step-by-step numbered instructions (≥5 steps) with specifics
- **Basic**: Simple step list (3-4 steps) or brief assembly overview
- **Referenced**: Points to external assembly guide/video/document
- **None**: No assembly information

### Design Files
- **CAD Files**: .dwg, .step, .iges, .f3d, .sldprt, .catpart
- **PCB Files**: .kicad, .sch, .brd, .gerber, .eagle
- **3D Files**: .stl, .obj, .3mf, .amf
- **Other**: .pdf technical drawings, .dxf, etc.

## Confidence Scoring (0-100)
- **90-100**: Explicit, unambiguous evidence with exact quotes
- **70-89**: Clear evidence but requires minimal interpretation  
- **50-69**: Contextual evidence requiring moderate interpretation
- **30-49**: Weak signals or ambiguous references
- **10-29**: Speculative based on limited context
- **0-9**: No credible evidence

## Required JSON Schema:

```json
{
  "document_metadata": {
    "total_word_count": number,
    "contains_technical_language": boolean,
    "primary_language": "english|non_english|mixed",
    "project_type": "hardware_only|software_only|mixed|unclear",
    "document_structure_quality": "well_structured|basic_structure|poor_structure"
  },
  "license_information": {
    "general_license": {
      "present": boolean,
      "type": "explicit|referenced|implied",
      "license_name": "string or null",
      "evidence_full": "complete relevant text",
      "evidence_location": "string (section/line reference)",
      "confidence_score": number,
      "confidence_rationale": "explicit_mention|contextual_inference|weak_signal"
    }
  },
  "contributing_guidelines": {
    "present": boolean,
    "level": number,
    "location_type": "inline_detailed|inline_brief|external_reference|none",
    "evidence_full": "complete relevant text",
    "evidence_location": "string",
    "confidence_score": number,
    "confidence_rationale": "string"
  },
  "bill_of_materials": {
    "present": boolean,
    "completeness_level": "complete|basic|partial|none",
    "format_type": "table|bulleted_list|numbered_list|paragraph|none",
    "total_components": number,
    "components": [
      {
        "component_name": "string",
        "quantity": "string or null",
        "specifications": "string or null", 
        "sourcing_info": "string or null",
        "source_line_full": "complete line/row from README"
      }
    ],
    "evidence_full": "complete BOM section text",
    "evidence_location": "string",
    "confidence_score": number,
    "confidence_rationale": "string",
    "multiple_boms_detected": boolean,
    "conflicting_info": boolean
  },
  "assembly_instructions": {
    "present": boolean,
    "detail_level": "detailed|basic|referenced|none",
    "instruction_format": "numbered_steps|bulleted_steps|paragraph|external_link|none",
    "step_count": number,
    "evidence_full": "complete assembly section text",
    "evidence_location": "string",
    "confidence_score": number,
    "confidence_rationale": "string"
  },
  "design_files": {
    "hardware_design_files": {
      "present": boolean,
      "file_categories": ["CAD|PCB|3D|Other"],
      "specific_formats": ["string"],
      "file_locations": ["string"],
      "evidence_full": "complete file reference text",
      "evidence_location": "string",
      "confidence_score": number,
      "confidence_rationale": "string"
    },
    "mechanical_design_files": {
      "present": boolean,
      "file_categories": ["CAD|3D|Technical_drawings|Other"],
      "specific_formats": ["string"],
      "file_locations": ["string"], 
      "evidence_full": "complete file reference text",
      "evidence_location": "string",
      "confidence_score": number,
      "confidence_rationale": "string"
    }
  },
  "specific_licenses": {
    "hardware_license": {
      "present": boolean,
      "license_name": "string or null",
      "license_type": "copyleft|permissive|proprietary|unclear|null",
      "evidence_full": "complete relevant text",
      "evidence_location": "string",
      "confidence_score": number,
      "confidence_rationale": "string"
    },
    "software_license": {
      "present": boolean,
      "license_name": "string or null", 
      "license_type": "copyleft|permissive|proprietary|unclear|null",
      "evidence_full": "complete relevant text",
      "evidence_location": "string",
      "confidence_score": number,
      "confidence_rationale": "string"
    },
    "documentation_license": {
      "present": boolean,
      "license_name": "string or null",
      "license_type": "copyleft|permissive|proprietary|unclear|null", 
      "evidence_full": "complete relevant text",
      "evidence_location": "string",
      "confidence_score": number,
      "confidence_rationale": "string"
    }
  },
  "validation_checks": {
    "readme_sections_identified": ["string"],
    "contradictory_information_detected": boolean,
    "incomplete_information_flagged": boolean,
    "classification_boundary_cases": ["string"],
    "evidence_verification_notes": "string"
  }
}
```

## Critical Instructions:

1. **Evidence Completeness**: Include the complete relevant text, not truncated quotes. If a section is >500 characters, include the full section and note the length.

2. **Operational Adherence**: Strictly follow the operational definitions. If something falls between categories, document this in validation_checks.

3. **Quantitative Confidence**: Use the 0-100 scale with explicit rationale. Anchor your scores to the defined ranges.

4. **Multiple Instance Handling**: If multiple BOMs, licenses, or conflicting information exists, document all instances and set conflicting_info flag.

5. **Boundary Case Documentation**: When classification is uncertain or falls between definitions, explicitly note this in classification_boundary_cases.

6. **Evidence Verification**: Only include evidence that actually exists in the provided text. If you reference something, it must be directly quotable from the source.

7. **Systematic Consistency**: Apply the same classification criteria throughout. If uncertain about a boundary case, err toward the lower/more conservative classification.

8. **Context Preservation**: Include enough surrounding context in evidence_full that another researcher could verify your classification.

## Examples:

### Example 1: Comprehensive Hardware Project

**README Content:**
```
# Arduino Weather Station v2.1

## License
Software: MIT License (see LICENSE-SOFTWARE.txt)
Hardware: CERN-OHL-W v2 (see LICENSE-HARDWARE.txt)  
Documentation: CC BY-SA 4.0

## Bill of Materials
| Component | Qty | Part Number | Supplier | Notes |
|-----------|-----|-------------|----------|--------|
| Arduino Uno R3 | 1 | A000066 | Arduino.cc | Main controller |
| DHT22 Sensor | 1 | AM2302 | Adafruit | Temp/humidity |
| 0.96" OLED | 1 | SSD1306 | Various | I2C display |
| 10kΩ Resistors | 2 | CFR-25JB-52-10K | Yageo | Pull-up resistors |

## Assembly Instructions
1. Solder headers to Arduino Uno if not pre-installed
2. Connect DHT22 VCC to Arduino 5V, GND to GND
3. Connect DHT22 data pin to Arduino digital pin 2
4. Connect OLED VCC to 3.3V, GND to GND  
5. Connect OLED SDA to Arduino A4, SCL to A5
6. Install 10kΩ pull-up resistors on SDA and SCL lines
7. Upload firmware using Arduino IDE
8. Test all sensor readings before final assembly

## Design Files
- `/hardware/pcb/weather_station.kicad_pro` - KiCad project file
- `/hardware/pcb/gerbers/` - Manufacturing files  
- `/mechanical/enclosure.step` - 3D printable case
- `/docs/schematic.pdf` - Circuit diagram

## Contributing
Please read CONTRIBUTING.md for our coding standards, pull request process, and code of conduct. All contributions must include tests and documentation updates.
```

**Expected Output:**
```json
{
  "document_metadata": {
    "total_word_count": 185,
    "contains_technical_language": true,
    "primary_language": "english", 
    "project_type": "mixed",
    "document_structure_quality": "well_structured"
  },
  "license_information": {
    "general_license": {
      "present": true,
      "type": "explicit",
      "license_name": "Multiple licenses specified",
      "evidence_full": "Software: MIT License (see LICENSE-SOFTWARE.txt)\nHardware: CERN-OHL-W v2 (see LICENSE-HARDWARE.txt)\nDocumentation: CC BY-SA 4.0",
      "evidence_location": "License section",
      "confidence_score": 95,
      "confidence_rationale": "explicit_mention"
    }
  },
  "contributing_guidelines": {
    "present": true,
    "level": 2,
    "location_type": "external_reference",
    "evidence_full": "Please read CONTRIBUTING.md for our coding standards, pull request process, and code of conduct. All contributions must include tests and documentation updates.",
    "evidence_location": "Contributing section",
    "confidence_score": 90,
    "confidence_rationale": "explicit_mention"
  },
  "bill_of_materials": {
    "present": true,
    "completeness_level": "complete",
    "format_type": "table",
    "total_components": 4,
    "components": [
      {
        "component_name": "Arduino Uno R3",
        "quantity": "1",
        "specifications": "A000066",
        "sourcing_info": "Arduino.cc",
        "source_line_full": "| Arduino Uno R3 | 1 | A000066 | Arduino.cc | Main controller |"
      },
      {
        "component_name": "DHT22 Sensor", 
        "quantity": "1",
        "specifications": "AM2302",
        "sourcing_info": "Adafruit",
        "source_line_full": "| DHT22 Sensor | 1 | AM2302 | Adafruit | Temp/humidity |"
      },
      {
        "component_name": "0.96\" OLED",
        "quantity": "1", 
        "specifications": "SSD1306",
        "sourcing_info": "Various",
        "source_line_full": "| 0.96\" OLED | 1 | SSD1306 | Various | I2C display |"
      },
      {
        "component_name": "10kΩ Resistors",
        "quantity": "2",
        "specifications": "CFR-25JB-52-10K",
        "sourcing_info": "Yageo", 
        "source_line_full": "| 10kΩ Resistors | 2 | CFR-25JB-52-10K | Yageo | Pull-up resistors |"
      }
    ],
    "evidence_full": "## Bill of Materials\n| Component | Qty | Part Number | Supplier | Notes |\n|-----------|-----|-------------|----------|--------|\n| Arduino Uno R3 | 1 | A000066 | Arduino.cc | Main controller |\n| DHT22 Sensor | 1 | AM2302 | Adafruit | Temp/humidity |\n| 0.96\" OLED | 1 | SSD1306 | Various | I2C display |\n| 10kΩ Resistors | 2 | CFR-25JB-52-10K | Yageo | Pull-up resistors |",
    "evidence_location": "Bill of Materials section", 
    "confidence_score": 95,
    "confidence_rationale": "explicit_mention",
    "multiple_boms_detected": false,
    "conflicting_info": false
  },
  "assembly_instructions": {
    "present": true,
    "detail_level": "detailed", 
    "instruction_format": "numbered_steps",
    "step_count": 8,
    "evidence_full": "## Assembly Instructions\n1. Solder headers to Arduino Uno if not pre-installed\n2. Connect DHT22 VCC to Arduino 5V, GND to GND\n3. Connect DHT22 data pin to Arduino digital pin 2\n4. Connect OLED VCC to 3.3V, GND to GND\n5. Connect OLED SDA to Arduino A4, SCL to A5\n6. Install 10kΩ pull-up resistors on SDA and SCL lines\n7. Upload firmware using Arduino IDE\n8. Test all sensor readings before final assembly",
    "evidence_location": "Assembly Instructions section",
    "confidence_score": 95,
    "confidence_rationale": "explicit_mention"
  },
  "design_files": {
    "hardware_design_files": {
      "present": true,
      "file_categories": ["PCB"],
      "specific_formats": ["kicad_pro", "gerbers", "pdf"],
      "file_locations": ["/hardware/pcb/weather_station.kicad_pro", "/hardware/pcb/gerbers/", "/docs/schematic.pdf"],
      "evidence_full": "- `/hardware/pcb/weather_station.kicad_pro` - KiCad project file\n- `/hardware/pcb/gerbers/` - Manufacturing files\n- `/docs/schematic.pdf` - Circuit diagram",
      "evidence_location": "Design Files section",
      "confidence_score": 95,
      "confidence_rationale": "explicit_mention"
    },
    "mechanical_design_files": {
      "present": true,
      "file_categories": ["CAD"],
      "specific_formats": ["step"],
      "file_locations": ["/mechanical/enclosure.step"],
      "evidence_full": "- `/mechanical/enclosure.step` - 3D printable case",
      "evidence_location": "Design Files section", 
      "confidence_score": 95,
      "confidence_rationale": "explicit_mention"
    }
  },
  "specific_licenses": {
    "hardware_license": {
      "present": true,
      "license_name": "CERN-OHL-W v2",
      "license_type": "copyleft",
      "evidence_full": "Hardware: CERN-OHL-W v2 (see LICENSE-HARDWARE.txt)",
      "evidence_location": "License section",
      "confidence_score": 95,
      "confidence_rationale": "explicit_mention"
    },
    "software_license": {
      "present": true,
      "license_name": "MIT License", 
      "license_type": "permissive",
      "evidence_full": "Software: MIT License (see LICENSE-SOFTWARE.txt)",
      "evidence_location": "License section",
      "confidence_score": 95,
      "confidence_rationale": "explicit_mention"
    },
    "documentation_license": {
      "present": true,
      "license_name": "CC BY-SA 4.0",
      "license_type": "copyleft",
      "evidence_full": "Documentation: CC BY-SA 4.0", 
      "evidence_location": "License section",
      "confidence_score": 95,
      "confidence_rationale": "explicit_mention"
    }
  },
  "validation_checks": {
    "readme_sections_identified": ["License", "Bill of Materials", "Assembly Instructions", "Design Files", "Contributing"],
    "contradictory_information_detected": false,
    "incomplete_information_flagged": false, 
    "classification_boundary_cases": [],
    "evidence_verification_notes": "All evidence directly quoted from source text. High confidence across all categories due to explicit, well-structured information."
  }
}
```

---

**README Content to Analyze:**
[INSERT README CONTENT HERE]