"""
XSD to JSON hierarchy 
-------------------------------------------------------------------------------------
Nested parent to child relationship as part of the JSON hierarch to be parsed by a
javascript tool and display as an interactive graph.

- Each parsed part of the XSD is assigned a "kind" value:
    - "element" is an XSD element that has a name, type, and children
    - "attribute" is an XSD attribute which is a child of an element and has a value
    - "base" is a complexType which can be extended by another type (inheritance)
- Substitution groups are mapped and built into the hierarchy recursively
- Abstract elements have a "base" child inheriting the head's complexType content
- Descriptions come from <xsd:annotation><xsd:documentation>
    - If a line starts with "Description=", use the part after '=' to populate
    - This is the incosnsistency between the old and new/modified schemas
- Tier number is pulled if present in the documentation tags
- At the end, merge all first-tier elements into OME root node
- Apply coloring based on node names (this still needs development)
- Parsing of names to be more human readable:
    - Remove leading '@'
    - Insert a space before a Capital following a lowercase but ID stays ID
"""

import re
import sys
import json
import lxml.etree as ET
from   pathlib      import Path
from   typing       import Optional, Dict, List, Set


# --- Configuration & Styling ---
XSD_NS = "http://www.w3.org/2001/XMLSchema"
QN = lambda local: f"{{{XSD_NS}}}{local}"

STYLE_MAP = {
    "OME": "#c6e46a",
    "Instrument": "#84a12f",
    "Image": "#E5828C",
    "DEFAULT": "#4b6cb7"
}

MAIN_NODES = {
    "OME", "Project", "Dataset", "Folder", "Experiment", "Plate", 
    "Screen", "Experimenter", "ExperimenterGroup", "Instrument", 
    "Image", "StructuredAnnotations", "ROI"
}

NAME_SPACING_RE = re.compile(r'([a-z])([A-Z])')

def normalize_name(name: str) -> str:
    """Reformats names into space-separated strings, preserving ID/UUID."""
    if name in ["ID", "UUID"]:
        return name
    name = re.sub(r'([a-zA-Z])(ID)$', r'\1 ID', name)
    return NAME_SPACING_RE.sub(r'\1 \2', name)

class OME_XSDParser:
    """Parser for OME XSD that captures structural hierarchy and metadata (Description/Tier)."""
    
    def __init__(self, xsd_path: Path):
        self.tree = ET.parse(str(xsd_path))
        self.root = self._find_schema_root()
        self.maps = self._build_global_maps()
        self.substitutions = self._build_substitution_map()

    def _find_schema_root(self) -> ET.Element:
        root = self.tree.getroot()
        return root if root.tag == QN("schema") else root.find(".//" + QN("schema"))

    def _build_global_maps(self) -> Dict[str, Dict[str, ET.Element]]:
        keys = ["element", "complexType", "group", "attribute", "attributeGroup"]
        maps = {k: {} for k in keys}
        for child in self.root:
            if not isinstance(child.tag, str): continue
            tag_local = ET.QName(child).localname
            name = child.get("name")
            if tag_local in maps and name:
                maps[tag_local][name] = child
        return maps

    def _build_substitution_map(self) -> Dict[str, List[ET.Element]]:
        sub_map = {}
        for el in self.root.findall(QN("element")):
            head = el.get("substitutionGroup")
            if head:
                sub_map.setdefault(head.split(":")[-1], []).append(el)
        return sub_map

    def get_metadata(self, node: ET.Element) -> Dict[str, Optional[str]]:
        """
        Extracts 'Description=' and 'Tier=' from xsd:documentation tags.
        
        Args:
            node: The XML element to scan for annotations.
        Returns:
            A dictionary containing 'description' and 'tier'.
        """
        meta = {"description": None, "tier": None}
        if node is None: return meta
        
        # Documentation is usually inside an annotation tag [cite: 15, 104]
        doc_elements = node.findall(f".//{QN('documentation')}")
        all_text = []
        
        for doc in doc_elements:
            text = "".join(doc.itertext()).strip()
            if not text: continue
            
            # Use regex to find Description= and Tier= patterns [cite: 42, 43, 105]
            desc_match = re.search(r'Description\s*=\s*(.*)', text, re.I | re.S)
            tier_match = re.search(r'Tier\s*=\s*(\d+)', text, re.I)
            
            if desc_match:
                meta["description"] = desc_match.group(1).strip()
            if tier_match:
                meta["tier"] = tier_match.group(1).strip()
            
            # If it's just general text without a key, save it as a fallback
            if not desc_match and not tier_match:
                all_text.append(text)
        
        # Fallback: if no explicit 'Description=' was found, use all documentation text 
        if not meta["description"] and all_text:
            meta["description"] = " ".join(all_text)
            
        return meta

    def resolve_element(self, el_node: ET.Element, seen_types: Set[str] = None) -> Dict:
        """Resolves an element, capturing its metadata and flattening its hierarchy."""
        seen_types = seen_types or set()
        
        ref_attr = el_node.get("ref")
        if ref_attr:
            ref_name = ref_attr.split(":")[-1]
            target_node = self.maps["element"].get(ref_name)
            return self.resolve_element(target_node, seen_types) if target_node is not None else {"name": ref_name, "children": []}

        name = el_node.get("name", "Unknown")
        is_abstract = el_node.get("abstract") == "true"
        
        # Capture Description and Tier for this node [cite: 43, 117]
        meta = self.get_metadata(el_node)
        
        node = {
            "kind": "element",
            "name": name,
            "description": meta["description"],
            "tier": meta["tier"],
            "children": []
        }

        if not is_abstract:
            attrs, elements = [], []
            type_name = el_node.get("type")
            
            # Named complexType resolution
            if type_name:
                type_key = type_name.split(":")[-1]
                if type_key in self.maps["complexType"] and type_key not in seen_types:
                    seen_types.add(type_key)
                    # Also try to pull metadata from the complexType definition itself if the element lacked it
                    if not node["description"] or not node["tier"]:
                        ct_meta = self.get_metadata(self.maps["complexType"][type_key])
                        if not node["description"]: node["description"] = ct_meta["description"]
                        if not node["tier"]: node["tier"] = ct_meta["tier"]
                        
                    self._collect_ordered_content(self.maps["complexType"][type_key], attrs, elements, seen_types)
                    seen_types.remove(type_key)
            
            # Anonymous complexType resolution
            anon_ct = el_node.find(QN("complexType"))
            if anon_ct is not None:
                self._collect_ordered_content(anon_ct, attrs, elements, seen_types)
            
            node["children"] = attrs + elements

        # Substitution Members
        if name in self.substitutions:
            for sub_el in self.substitutions[name]:
                node["children"].append(self.resolve_element(sub_el, seen_types))

        return node

    def _collect_ordered_content(self, parent_node: ET.Element, attrs: List, elements: List, seen_types: Set[str]):
        """Helper to walk the XSD and bucket attributes and elements separately."""
        for child in parent_node:
            if not isinstance(child.tag, str): continue
            tag_local = ET.QName(child).localname
            
            if tag_local == "extension":
                base_name = child.get("base", "").split(":")[-1]
                if base_name in self.maps["complexType"] and base_name not in seen_types:
                    seen_types.add(base_name)
                    self._collect_ordered_content(self.maps["complexType"][base_name], attrs, elements, seen_types)
                    seen_types.remove(base_name)
                self._collect_ordered_content(child, attrs, elements, seen_types)

            elif tag_local == "attribute":
                name = child.get("name") or child.get("ref", "").split(":")[-1]
                attr_meta = self.get_metadata(child)
                attrs.append({
                    "kind": "attribute", 
                    "name": name, 
                    "description": attr_meta["description"],
                    "tier": attr_meta["tier"],
                    "children": []
                })

            elif tag_local == "element":
                elements.append(self.resolve_element(child, seen_types))

            elif tag_local in ["sequence", "choice", "complexContent", "simpleContent", "group"]:
                self._collect_ordered_content(child, attrs, elements, seen_types)


# --- Post-Parsing Styling & Normalization ---

def lighten(hex_color: str, amt: float = 0.25) -> str:
    h = hex_color.lstrip('#')
    rgb = [int(h[i:i+2], 16) for i in (0, 2, 4)]
    res = [int(c + (255 - c) * amt) for c in rgb]
    return "#{:02X}{:02X}{:02X}".format(*[min(255, val) for val in res])

def finalize_tree(node: Dict, current_color: str):
    """Recursively finalizes names and styling across the hierarchy."""
    node["name"] = normalize_name(node["name"])
    node["color"] = current_color
    
    for child in node.get("children", []):
        if child.get("kind") == "attribute":
            finalize_tree(child, current_color)
        else:
            finalize_tree(child, lighten(current_color, 0.15))

def run_parser(input_xsd: str, output_json: str):
    """Execution logic for parsing and saving."""
    input_path = Path(input_xsd)
    output_path = Path(output_json)

    if not input_path.exists():
        print(f"Error: Input file {input_path} not found.")
        return

    print(f"Reading from: {input_path.resolve()}")
    parser = OME_XSDParser(input_path)
    
   # Parse OME as the Root
    ome_node = parser.resolve_element(parser.maps["element"]["OME"])
    
    # Check for duplicates and ensure the main nodes are present
    existing_children = {c["name"] for c in ome_node["children"]}
    for name in MAIN_NODES:
        if name != "OME" and name not in existing_children:
            node = parser.resolve_element(parser.maps["element"][name])
            ome_node["children"].append(node)

    # Apply final styles
    ome_node["color"] = STYLE_MAP["OME"]
    for child in ome_node.get("children", []):
        # Look up color based on original element name before spacing is applied
        branch_color = STYLE_MAP.get(child["name"], STYLE_MAP["DEFAULT"])
        # Applies spacing to node names for human readability
        finalize_tree(child, branch_color)

    # Rename OME Root node to LiMi Model
    ome_node["name"] = "LiMi Model"

    # Export
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(ome_node, f, indent=2)
    print(f"Successfully saved to: {output_path.resolve()}")


def main():

    """Handles argument passing."""
    # Check for CLI arguments: script.py <input> <output>
    if len(sys.argv) >= 3:
        run_parser(sys.argv[1], sys.argv[2])
    
    elif len(sys.argv) == 2:
        # Default output name if only input is provided
        run_parser(sys.argv[1], "LiMi_Model.json")
    
    else:
        # Look for defaults in current directory if no arguments are given
        print("Usage: python script.py <input_path> <output_path>")
        print("Checking current directory for 'XMLSchema1.xsd'...")
        default_in = "LiMi_XMLSchema.xsd"
        default_out = "LiMi_Model.json"
        run_parser(default_in, default_out)

if __name__ == "__main__":
    main()