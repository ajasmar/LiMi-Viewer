# LiMi Metadata Model Viewer
An interactive web-based visualization tool that for viewing the LiMi Metadata Model.

The tool consists of a D3.js-based collapsible node-linked graph built using a hierarchical JSON input. The JSON input is created using a python script which parses the XSD (XML Schema Definition) file.

The current version was used to parse the latest XSD available from the NBOMicroscopyMetadataSpecs github 
(Model/in progress/v02-10/NBO_MicroscopyMetadataSpecifications_ALL.xsd)

A live view of the current version can be found at this [GitHub page](https://ajasmar.github.io/LiMi-Viewer/).

<img width="1835" height="865" alt="image" src="https://github.com/user-attachments/assets/260f0807-22c5-446c-9ddd-5235b5817fff" />


---
# Structure
```text
LiMi-Viewer/
├── data/                       
│   ├── LiMi_Model.json         # Generated JSON outputs
│   └── LiMi_Model_Schema.json  # JSON Schema for Validation
├── schemas/                    
│   └── LiMi_XMLSchema.xsd      # Source XSD files
├── scripts/                    
│   └── LiMi_XSDparser.py       # Python XSD to JSON Parser
├── src/                        
│   ├── index.html              # Web Entry Point
│   └── LiMi_Viewer.js          # D3.js Visualization 
├── requirements.txt            # Python dependencies
└── README.md
```
---
# Running the Parsing
Install any requirements (lxml)
```
pip install -r requirements.txt
```
Run the script with its 2 arguements (input schema and output json)
```
python scripts/LiMi_XSDparser.py schemas/LiMi_XMLSchema.xsd data/LiMi_Model.json
```
---
# Running the Web Viewer
Run a local HTTP server in Python
```
python -m http.server 8000
```
Open http://localhost:8000/src/ in a browser
