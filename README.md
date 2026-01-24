# LiMi Metadata Model Viewer
An interactive web-based visualization tool that for viewing the LiMi Metadata Model.

The tool consists of a D3.js-based collapsible node-linked graph built using a hierarchical JSON input. The JSON input is created using a python script which parses the XSD (XML Schema Definition) file.

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
