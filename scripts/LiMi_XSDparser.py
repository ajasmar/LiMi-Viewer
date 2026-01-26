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
    - This is the incosnsistency between the old and new/modified elements
      which then requires merging at the end
- Tier number is pulled if present in the documentation tags
- At the end, merge all first-tier elements into the OME/LiMi root node
- Apply coloring based on node names (this still needs development)
- Parsing of names to be more human readable:
    - Remove leading '@'
    - Insert a space before a Capital following a lowercase but ID stays ID
"""

import re
import sys
import json
import lxml.etree   as ET
from   pathlib      import Path
from   typing       import Optional, Dict, List, Set

""" ------------------ Configuration and Styling Variables -------------------- """

XSD_NS = "http://www.w3.org/2001/XMLSchema"
QN = lambda local: f"{{{XSD_NS}}}{local}" # Qualified Name (QName) helper

# Defined hex color mapping for categorical visualization
# This is where I was having issues
CATEGORIES = {
    "IMAGE_ROOT": "#c6e46a",
    "IMAGE_STRUCT": {"el": "#65AC6E", "attr": "#84c192"},
    "SETTINGS": {"el": "#B6DC3F", "attr": "#d6eb92"},
    "SPECIMEN": {"el": "#DCCC36", "attr": "#e5d968"},
    "IMAGE_OTHER": "#D3EA8B",
    "EXPERIMENTAL": {"el": "#D37C38", "attr": "#e1a171"},
    "SAMPLE": {"el": "#FBAE4D", "attr": "#fbc681"},
    "INSTRUMENT_ROOT": "#84a12f",
    "INSTRUMENT_ABS": "#91B033",
    "INSTRUMENT_CHILD": "#c3d97f",
    "INSTRUMENT_ATTR": "#D8E6AC",
    "CALIBRATION_ROOT": "#E5828C",
    "DEFAULT": "#D3EA8B"
}

# Upper level container elements in the LiMi Model
MAIN_NODES = {
    "OME", "Project", "Dataset", "Folder", "Experiment", "Plate", 
    "Screen", "Experimenter", "ExperimenterGroup", "Instrument", 
    "Image", "StructuredAnnotations", "ROI"
}

# Regex for human-readable spacing (e.g., ExperimenterGroup -> Experimenter Group)
NAME_SPACING_RE = re.compile(r'([a-z])([A-Z])')

class OME_XSDParser:
    """
    The parser for the OME XSD schema that transforms an XML structure 
    into a JSON hierarchy. It captures the name, type, description, and tier
    of each "node" and maps out the children.
    """
    
    def __init__(self, xsd_path: Path):
        """
        Initializes the parser and builds internal lookup maps.
        
        Args:
            xsd_path: Path object pointing to the source XML Schema file.
        """
        self.tree = ET.parse(str(xsd_path))
        self.root = self._find_schema_root()
        self.maps = self._build_global_maps()
        self.substitutions = self._build_substitution_map()

    def _find_schema_root(self) -> ET.Element:
        """
        Locates the top-level <xsd:schema> element.
        
        Returns:
            The root schema Element object.
        """
        root = self.tree.getroot()
        return root if root.tag == QN("schema") else root.find(".//" + QN("schema"))

    def _build_global_maps(self) -> Dict[str, Dict[str, ET.Element]]:
        """
        Indexes all global declarations.
        
        Returns:
            A dictionary containing maps for 'element', 'complexType', 'group', etc.
        """
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
        """
        Identifies all elements belonging to a substitutionGroup.
        
        This allows the parser to resolve abstract heads into their concrete 
        members.
        
        Returns:
            A map where keys are head element names and values are
            lists of member elements.
        """
        sub_map = {}
        for el in self.root.findall(QN("element")):
            head = el.get("substitutionGroup")
            if head:
                sub_map.setdefault(head.split(":")[-1], []).append(el)
        return sub_map

    def get_metadata(self, node: ET.Element) -> Dict[str, Optional[str]]:
        """
        Extracts documentation and tier information from a node's annotation block.
        
        This method targets the node's immediate documentation
        and uses regular expressions to isolate 'Description=' and 'Tier=' fields 
        without capturing documentation from nested child nodes. This was an issue
        with the original logic for parsing the inheritance after refactoring.
        
        Args:
            node: The XML element to scan.
            
        Returns:
            A dictionary with keys 'description' and 'tier'.
        """
        meta = {"description": None, "tier": None}
        if node is None: return meta
        
        # Find only direct children to avoid capturing nested field docs
        doc_elements = node.findall(f"./{QN('annotation')}/{QN('documentation')}")
        all_text = []
        
        for doc in doc_elements:
            text = "".join(doc.itertext()).strip()
            if not text: continue
            
            # Used to capture large multi <xsd:documentation> blocks
            desc_match = re.search(r'Description\s*=\s*(.*)', text, re.I | re.S)
            tier_match = re.search(r'Tier\s*=\s*(\d+)', text, re.I)
            
            if desc_match:
                meta["description"] = desc_match.group(1).strip()
            if tier_match:
                meta["tier"] = tier_match.group(1).strip()
            
            if not desc_match and not tier_match:
                all_text.append(text)
        
        # Fallback if no 'Description=' tag was found
        if not meta["description"] and all_text:
            meta["description"] = " ".join(all_text)
            
        return meta

    def resolve_element(self, el_node: ET.Element, seen_types: Set[str] = None) -> Dict:
        """
        Recursively resolves an XSD element into its JSON hierarchical representation.
        
        Processing steps:
        1. Resolves references (@ref) by jumping to global definitions.
        2. Captures node-specific metadata (Description/Tier).
        3. Flattens inheritance by resolving 'complexType' extensions 
           directly into the node.
        4. Suppresses attribute collection for abstract nodes to prevent 
           data duplication.
        
        Args:
            el_node: The lxml element to process.
            seen_types: Recursion tracker to prevent loops in complexType extensions.
            
        Returns:
            A dictionary containing kind, name, metadata, and ordered children.
        """
        seen_types = seen_types or set()
        
        ref_attr = el_node.get("ref")
        if ref_attr:
            ref_name = ref_attr.split(":")[-1]
            target_node = self.maps["element"].get(ref_name)
            return self.resolve_element(target_node, seen_types) if target_node is not None else {"name": ref_name, "children": []}

        name = el_node.get("name", "Unknown")
        is_abstract = el_node.get("abstract") == "true"
        meta = self.get_metadata(el_node)
        
        node = {
            "kind": "element", "name": name, "description": meta["description"],
            "tier": meta["tier"], "is_abstract": is_abstract, "children": []
        }

        if not is_abstract:
            attrs, elements = [], []
            type_name = el_node.get("type")
            if type_name:
                type_key = type_name.split(":")[-1]
                if type_key in self.maps["complexType"] and type_key not in seen_types:
                    seen_types.add(type_key)
                    # Use complexType documentation if the element lacks it
                    ct_meta = self.get_metadata(self.maps["complexType"][type_key])
                    if not node["description"]: node["description"] = ct_meta["description"]
                    if not node["tier"]: node["tier"] = ct_meta["tier"]
                        
                    self._collect_ordered_content(self.maps["complexType"][type_key], attrs, elements, seen_types)
                    seen_types.remove(type_key)
            
            anon_ct = el_node.find(QN("complexType"))
            if anon_ct is not None:
                self._collect_ordered_content(anon_ct, attrs, elements, seen_types)
            
            node["children"] = attrs + elements

        # Attach concrete members of abstract heads
        if name in self.substitutions:
            for sub_el in self.substitutions[name]:
                node["children"].append(self.resolve_element(sub_el, seen_types))
        return node

    def _collect_ordered_content(self, parent_node: ET.Element, attrs: List, elements: List, seen_types: Set[str]):
        """
        Reads structural tags to categorize children into 
        attributes vs. elements.
        
        This approach ensures that attributes are always displayed first 
        in the final JSON list, followed by sub-elements.
        
        Args:
            parent_node: The XML element containing structural tags.
            attrs: List to accumulate attribute nodes.
            elements: List to accumulate element nodes.
            seen_types: Recursion tracker for extensions.
        """
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
                    "kind": "attribute", "name": name, "description": attr_meta["description"],
                    "tier": attr_meta["tier"], "children": []
                })

            elif tag_local == "element":
                elements.append(self.resolve_element(child, seen_types))

            elif tag_local in ["sequence", "choice", "complexContent", "simpleContent", "group"]:
                self._collect_ordered_content(child, attrs, elements, seen_types)


""" -------------------- Post-Parsing Styling Functions ----------------------- """

def normalize_name(name: str) -> str:
    """
    Transforms PascalCase/camelCase names into space-separated strings
    with exceptions for acronyms like 'ID' and 'UUID'
    
    Args:
        name: The raw string from the XSD attribute or element name.
        
    Returns:
        A spaced string.
    """
    if name in ["ID", "UUID"]:
        return name
    name = re.sub(r'([a-zA-Z])(ID)$', r'\1 ID', name)
    return NAME_SPACING_RE.sub(r'\1 \2', name)

def get_node_color(node: Dict, context: str) -> str:
    """
    Applies the specific color palette based on the branch context.
    This is where some development and fixing will need to be done.
    
    Args:
        node: The node being styled.
        context: The top-level branch name defining the current palette.
        
    Returns:
        A hex color string corresponding to the node's functional category.
    """
    name, kind = node["name"], node["kind"]
    is_abstract = node.get("is_abstract", False)
    
    if context == "Instrument":
        if name == "Instrument": return CATEGORIES["INSTRUMENT_ROOT"]
        if kind == "attribute": return CATEGORIES["INSTRUMENT_ATTR"] 
        if is_abstract: return CATEGORIES["INSTRUMENT_ABS"]          
        return CATEGORIES["INSTRUMENT_CHILD"]                        

    if context == "Image":
        if any(x in name for x in ["Pixels", "Plane", "Channel"]):
            return CATEGORIES["IMAGE_STRUCT"]["attr" if kind == "attribute" else "el"]
        if "Settings" in name:
            return CATEGORIES["SETTINGS"]["attr" if kind == "attribute" else "el"]
        if any(x in name for x in ["Fluorophore", "Medium", "Immersion", "Label"]):
            return CATEGORIES["SPECIMEN"]["attr" if kind == "attribute" else "el"]
        return CATEGORIES["IMAGE_OTHER"]

    if context == "Experiment": return CATEGORIES["EXPERIMENTAL"]["attr" if kind == "attribute" else "el"]
    if context == "Sample": return CATEGORIES["SAMPLE"]["attr" if kind == "attribute" else "el"]
    
    return CATEGORIES["DEFAULT"]

def finalize_tree(node: Dict, context: str):
    """
    Recursively applies name spacing and consistent categorical coloring.
    
    Args:
        node: The node to finalize.
        context: The naming context of the current branch.
    """
    raw_name = node["name"]
    node["color"] = get_node_color(node, context)
    node["name"] = normalize_name(raw_name)
    
    node.pop("is_abstract", None)
    
    for child in node.get("children", []):
        finalize_tree(child, context)


""" ------------------------- Running the parser ------------------------- """

def run_parser(input_xsd: str, output_json: str):
    """
    Runs the full parsing and styling workflow.
    
    Args:
        input_xsd: Path to the XSD file.
        output_json: Target path for the JSON export.
    """
    input_path = Path(input_xsd)
    if not input_path.exists(): return

    parser = OME_XSDParser(input_path)
   
    ome_node = parser.resolve_element(parser.maps["element"]["OME"])
    
    # Integrate and deduplicate main model containers
    # This merges the old OME model with the updaed LiMi nodes
    existing_children = {c["name"] for c in ome_node["children"]}
    for name in MAIN_NODES:
        if name != "OME" and name not in existing_children:
            ome_node["children"].append(parser.resolve_element(parser.maps["element"][name]))

    # Apply contextual coloring starting from OME root
    ome_node["color"] = CATEGORIES["IMAGE_ROOT"]
    for child in ome_node.get("children", []):
        finalize_tree(child, child["name"])
    
    # Rename to custom root model name
    ome_node["name"] = "LiMi Model"

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(ome_node, f, indent=2)
    print(f"Workflow Complete: Spaced Names, Full Metadata, and Categorical Coloring applied. Saved to {output_json}")

def main():
    """Entry point handling CLI arguments or defaults."""
    if len(sys.argv) >= 3:
        run_parser(sys.argv[1], sys.argv[2])
    else:
        # Default portability if no args provided
        run_parser("XMLSchema1.xsd", "test_ome_refactor-coloring.json")

if __name__ == "__main__":
    main()