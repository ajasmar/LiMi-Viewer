// Model JSON
const DATA_URL = `./data/LiMi_Model.json`;

// Fetch root object and cache-bust via timestamp
function loadData() {
  const url = `${DATA_URL}?cb=${Date.now()}`; // avoid stale caches
  return fetch(url)
    .then(res => {
      if (!res.ok) throw new Error(`Failed to load ${url}`); // Return HTTP errors
      return res.json(); // parse JSON root object
    });
}

// Prevent d3.hierarchy from reading undefined.children
const childAccessor = d => Array.isArray(d?.children) ? d.children : [];

// Stable key per node using its ancestor path (names can repeat and keys can be used to save open/close state for output function) 
function uniqueKey(d) {
  return d.ancestors()
    .map(n => n.data?.name ?? "(unnamed)")
    .reverse()
    .join("/");
}

// Node label call
function nodeLabel(d) {
  return d.data?.name ?? "(unnamed)";
}

// Use color carried in the JSON data or fallback to default
function nodeFill(d) {
  if (d.data?.color) return d.data.color; // use color from JSON if present
  if (d.data?.kind === "attribute") return "#6fa8dc"; // attribute color
  if (d.depth === 0) return "#888"; // root fallback
  return "#4b6cb7"; // element/base fallback
}

// Info text fallback if a node has no parsed XSD description.
function describeNode(d) {
  const k = d.data?.kind || "element";
  if (k === "attribute") {
    const t = d.data.type ? `type=${d.data.type}` : "type=unspecified";
    const u = d.data.use ? `, use=${d.data.use}` : "";
    const def = d.data.default ? `, default=${d.data.default}` : "";
    const fx = d.data.fixed ? `, fixed=${d.data.fixed}` : "";
    const inh = d.data.inherited ? " (inherited)" : "";
    return `Attribute ${nodeLabel(d)} — ${t}${u}${def}${fx}${inh}`;
  }
  // Show type/baseType for automated description generation 
  const typeBits = [];
  if (d.data?.type) typeBits.push(`type=${d.data.type}`);
  if (d.data?.baseType) typeBits.push(`extends=${d.data.baseType}`);
  const occ = [
    d.data?.minOccurs != null ? `minOccurs=${d.data.minOccurs}` : null,
    d.data?.maxOccurs != null ? `maxOccurs=${d.data.maxOccurs}` : null
  ].filter(Boolean).join(", ");
  if (occ) typeBits.push(occ);

  return `Element ${nodeLabel(d)}${typeBits.length ? " — " + typeBits.join("; ") : ""}`;
}

// Add parsed description from JSON or fallback to describeNode() for default text
function getDescription(d) {
  let desc = (d.data?.description || "").trim?.();
  if (!desc) {
    desc = describeNode(d);
  }
  return desc;
}

// Escape text before injecting into HTML
function escapeHTML(s) {
  return String(s).replace(/[&<>"']/g, m =>
    ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;'
    } [m])
  );
}

const svg = d3.select("#chart");

// Ensure the SVG itself is responsive
// Height is statically set in here, but can be set to percentage if CSS set properly at HTML side
svg.attr("width", "100%").attr("height", 800);

const svgNode = svg.node();
let width = svgNode?.getBoundingClientRect().width || 1200;
let height = svgNode?.getBoundingClientRect().height || 800;

// Info box margin
const margin = { top: 20, right: 90, bottom: 150, left: 90 };

// Sets zoom layer for only the graph so that the info panel stays fixed
const zoomLayer = svg.append("g").attr("class", "zoom-layer");

// Graph container maintianing the margins independent of zoom
const container = zoomLayer.append("g")
  .attr("transform", `translate(${margin.left},${margin.top})`);

// Info panel background
const infoGroup = svg.append("g").attr("class", "info-panel");

// Background Rectangle
const infoRect = infoGroup.append("rect")
  .attr("fill", "#f9f9f9")
  .attr("stroke", "#ccc")
  .attr("rx", 8).attr("ry", 8);

// HTML-based wrapped/scrollable panel using foreignObject
const infoFO = infoGroup.append("foreignObject");

// Initialize info-box with strict flexible box structure
infoFO.append("xhtml:div")
  .attr("id", "info-box")
  .style("font-family", "sans-serif")
  .style("font-size", "12px")
  .style("line-height", "1.3")
  .style("color", "#000")
  .style("height", "100%")        // Fill the foreignObject completely
  .style("box-sizing", "border-box")
  .style("display", "flex")       // Enable flexbox
  .style("flex-direction", "column")
  .style("overflow", "hidden")    // Disable outer scrolling
  .html('<div style="color:#666; padding: 4px;">Click a node’s “| i” to see details.</div>');

// Resize handler to adjust Info Panel width/position dynamically 
function handleResize() {
  const bbox = svgNode.getBoundingClientRect();
  width = bbox.width || 1200;
  height = bbox.height || 800;

  const panelW = width - margin.left - margin.right;
  const panelH = margin.bottom - 20;
  const panelY = height - margin.bottom;

  // Update background rectangle
  infoRect
    .attr("x", margin.left)
    .attr("y", panelY)
    .attr("width", panelW)
    .attr("height", panelH);

  // Update text container
  infoFO
    .attr("x", margin.left + 8)
    .attr("y", panelY + 8)
    .attr("width", Math.max(0, panelW - 16)) // Prevent negative width
    .attr("height", Math.max(0, panelH - 16));
}

// Call to set initial size
handleResize();

// Attach listener to window resize
d3.select(window).on("resize", handleResize);

// Enable pan-and-zoom (applies to zoomLayer only and excludes the info box)
const zoom = d3.zoom()
  .scaleExtent([0.5, 2]) // min/max zoom
  .on("zoom", ({ transform }) => {
    zoomLayer.attr("transform", transform);
  });

// Activate zoom on the SVG (disable double click-to-zoom)
svg.call(zoom).on("dblclick.zoom", null);

// Container for generation of arrowheads
svg.select("defs").remove(); // remove any old arrowheads
const defs = svg.append("defs");
defs.append("marker")
  .attr("id", "arrow-subst")
  .attr("viewBox", "0 -5 10 10")
  .attr("refX", 0)
  .attr("refY", 0)
  .attr("markerUnits", "strokeWidth")
  .attr("markerWidth", 6)
  .attr("markerHeight", 6)
  .attr("orient", "auto")
  .append("path")
  .attr("d", "M10,-5L0,0L10,5")
  .attr("fill", "#999");

// Tree layout settings (edit here for spacing changes)
const verticalSpacing = 60;
const horizontalSpacing = 300;

const tree = d3.tree()
  .nodeSize([verticalSpacing, horizontalSpacing])
  .separation((a, b) => a.parent === b.parent ? 1 : 2);

// Node dimension store
const nodeDims = new Map();
const defaultWH = { w: 100, h: 26 };
const keyOf = d => uniqueKey(d);

function getH(d) { return nodeDims.get(keyOf(d))?.h ?? d.rectH ?? defaultWH.h; }
function getW(d) { return nodeDims.get(keyOf(d))?.w ?? d.rectW ?? defaultWH.w; }

function anchorLeft(d) { const w = getW(d); return { x: d.y, y: d.x }; }
function anchorRight(d) { const w = getW(d); return { x: d.y + w, y: d.x }; }

function measureAndCache(d, gEl) {
  const lbl = gEl.select("text.label").node();
  const btn = gEl.select("text.info-btn").node();
  const padX = 8, padY = 6;
  let w = defaultWH.w, h = defaultWH.h;
  if (lbl && btn) {
    const bb = lbl.getBBox();
    const bbBtn = btn.getBBox();
    w = bb.width + bbBtn.width + padX * 3;
    h = bb.height + padY * 2;
  }
  d.rectW = w; d.rectH = h;
  nodeDims.set(keyOf(d), { w, h });
}

// Calculation for the connecting line curving
function pathCubic(x1, y1, x2, y2) {
  // curveRatio > 0.5 pushes the curve inflection closer to the child (x2),
  // making the line come out straighter/longer from the parent (x1).
  const curveRatio = 0.75; 
  const xm = x1 + (x2 - x1) * curveRatio;
  return `M${x1},${y1}C${xm},${y1} ${xm},${y2} ${x2},${y2}`;
}

// Connecting line generation
function linkPathNormal(d) {
  const p = d.source, c = d.target;
  const a1 = anchorRight(p);
  const a2 = anchorLeft(c);
  return pathCubic(a1.x, a1.y, a2.x, a2.y);
}

function linkPathSubst(d) {
  const p = d.source, c = d.target;
  const a1 = anchorRight(c);
  const a2 = anchorLeft(p);
  return pathCubic(a1.x, a1.y, a2.x, a2.y);
}

function isSubstitutionEdge(d) { return !!d.target?.data?.substitution; }

function collapse(d) {
  if (d.children) {
    d._children = d.children;
    d._children.forEach(collapse);
    d.children = null;
  }
}

let root;

// Main render/update function
function update(source) {
  const layout = tree(root);
  const nodes = layout.descendants();
  const links = layout.links();

  const nodeSel = container.selectAll("g.node").data(nodes, uniqueKey);
  const enter = nodeSel.enter().append("g")
    .attr("class", "node")
    .attr("transform", `translate(${source.y0},${source.x0})`)
    .on("click", (e, d) => {
      if (d.children) { d._children = d.children; d.children = null; }
      else if (d._children) { d.children = d._children; d._children = null; }
      update(d);
      centerNode(d);
    });

  enter.append("rect")
    .attr("rx", 8).attr("ry", 8)
    .attr("stroke", "#333").attr("stroke-width", 1);

  enter.append("text")
    .attr("class", "label")
    .attr("text-anchor", "start")
    .attr("dominant-baseline", "middle")
    .attr("fill", "#000")
    .text(d => nodeLabel(d));

  // Info button
  enter.append('text')
    .attr('class', 'info-btn')
    .attr('text-anchor', 'start')
    .attr('font-weight', 'bold')
    .attr('fill', '#000')
    .style('cursor', 'pointer')
    .attr('font-size', '20px')
    .attr('dy', '0.25em')
    .text('| i')
    .on("click", (e, d) => {
      e.stopPropagation();
	  
	  // Check for Tier value and append to description title
      const hasTier = d.data?.tier !== undefined && d.data?.tier !== null;
      const tierValue = hasTier ? ` (Tier ${d.data.tier})` : "";
      
      const titleText = `Details for ${nodeLabel(d)}${tierValue}:`;
      const desc = getDescription(d);

      d3.select("#info-box").html(`
        <div style="
          flex: 0 0 auto;
          font-weight: bold; 
          margin-bottom: 12px; 
          border-bottom: 3px solid #000; 
          padding-bottom: 4px; 
          background: #f9f9f9;
        ">
          ${escapeHTML(titleText)}
        </div>
        <div style="
          flex: 1 1 auto;
          overflow-y: auto; 
          min-height: 0;
          padding-right: 4px;
        ">
          ${escapeHTML(desc).replace(/\n/g, "<br/>")}
        </div>
      `);
    });

  const nodeUpdate = enter.merge(nodeSel);
  nodeUpdate.select("rect").attr("fill", nodeFill);

  nodeUpdate.each(function(d) {
    const gEl = d3.select(this);
    measureAndCache(d, gEl);
    const w = d.rectW, h = d.rectH;
    gEl.select("rect").attr("width", w).attr("height", h).attr("x", 0).attr("y", -h / 2);
    const lbl = gEl.select("text.label");
    const btn = gEl.select("text.info-btn");
    const bb = lbl.node().getBBox();
    const padX = 8;
    lbl.attr("x", padX).attr("y", 0);
    btn.attr("x", padX * 2 + bb.width).attr("y", 0);
  });

  nodeUpdate.transition().duration(300).attr("transform", d => `translate(${d.y},${d.x})`);
  nodeSel.exit().transition().duration(300).attr("transform", `translate(${source.y},${source.x})`).remove();

  nodes.forEach(nd => {
    if (!nodeDims.has(keyOf(nd))) {
      nodeDims.set(keyOf(nd), { w: nd.rectW ?? defaultWH.w, h: nd.rectH ?? defaultWH.h });
    }
  });

  const linkSel = container.selectAll("path.link").data(links, d => uniqueKey(d.target));
  const linkEnter = linkSel.enter().insert("path", "g")
    .attr("class", "link")
    .attr("fill", "none")
    .attr("stroke", "#999")
    .attr("stroke-width", 2)
    .attr("d", d => {
      const p = d.source;
      const a = anchorRight(p);
      return pathCubic(a.x, a.y, a.x, a.y);
    });

  linkEnter.merge(linkSel).transition().duration(300)
    .attr("marker-end", d => isSubstitutionEdge(d) ? "url(#arrow-subst)" : null)
    .attr("d", d => isSubstitutionEdge(d) ? linkPathSubst(d) : linkPathNormal(d));

  linkSel.exit().transition().duration(300)
    .attr("d", d => isSubstitutionEdge(d) ? linkPathSubst(d) : linkPathNormal(d))
    .remove();

  nodes.forEach(d => { d.x0 = d.x; d.y0 = d.y; });
}

// Function for cetering on the selected node
function centerNode(d) {
  const t = d3.zoomTransform(svg.node());
  const k = t.k;
  const targetX = margin.left + d.y;
  const targetY = margin.top + d.x;
  const tx = width / 2 - k * targetX;
  const ty = height / 2 - k * targetY;
  svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(k));
}

// Function to re-generate the graph and center
function redraw() {
  loadData().then(data => {
    root = d3.hierarchy(data, childAccessor);
    root.x0 = 0; root.y0 = 0;
    if (root.children) root.children.forEach(collapse);
    update(root);
    centerNode(root);
  }).catch(console.error);
}

redraw();

/// Search Functions
let searchResults = [];
let currentSearchIndex = 0;
let lastSearchTerm = "";

function searchNode(term) {
  if (!root) return;
  const searchTerm = term ? term.toLowerCase().trim() : "";

  if (searchTerm === "") {
    resetTree();
    return;
  }

  // Cycle to the next result when searching the same term again
  if (searchTerm === lastSearchTerm && searchResults.length > 0) {
    currentSearchIndex = (currentSearchIndex + 1) % searchResults.length;
    focusOnResult(currentSearchIndex);
    return;
  }

  // Reset states for new search
  lastSearchTerm = searchTerm;
  searchResults = [];
  currentSearchIndex = 0;

  // Recursive function returning true if the node or any descendant is a match
  function filterTree(node) {
    const name = nodeLabel(node).toLowerCase();
    const isMatch = name.includes(searchTerm);
    
    if (isMatch) {
      searchResults.push(node);
    }

    let hasMatchingDescendant = false;

    // Combine currently expanded and collapsed children to check the whole subtree
    const allChildren = [];
    if (node.children) allChildren.push(...node.children);
    if (node._children) allChildren.push(...node._children);

    if (allChildren.length > 0) {
      const visibleChildren = [];
      const hiddenChildren = [];

      // Evaluate every child branch
      allChildren.forEach(child => {
        const childContainsMatch = filterTree(child);
        if (childContainsMatch) {
          hasMatchingDescendant = true;
          visibleChildren.push(child); // Keep this branch open
        } else {
          hiddenChildren.push(child);  // Collapse this branch
        }
      });

      // Apply the new visibility states to the node
      if (visibleChildren.length > 0) {
        node.children = visibleChildren;
        node._children = hiddenChildren.length > 0 ? hiddenChildren : null;
      } else {
        node.children = null;
        node._children = hiddenChildren.length > 0 ? hiddenChildren : null;
      }
    }

    // Return true up the chain if this node or any of its children match
    return isMatch || hasMatchingDescendant;
  }

  // Run the filter starting at the root
  filterTree(root);

  const statusEl = d3.select("#search-status");

  if (searchResults.length > 0) {
    // Update the graph
    update(root);

    // Highlight matches and focus on the first one
    highlightAllMatches();
    setTimeout(() => focusOnResult(0), 300);
    
  } else {
    // If no matches, clear highlights and collapse everything
    clearHighlights();
    statusEl.text("No matches found.");
    collapseAll(root);
    update(root);
    centerNode(root);
  }
}

// Fully collapse a subtree
function collapseAll(d) {
  if (d.children) {
    d._children = d.children;
    d._children.forEach(collapseAll);
    d.children = null;
  } else if (d._children) {
    d._children.forEach(collapseAll);
  }
}

// Center view and update text counter
function focusOnResult(index) {
  if (searchResults.length === 0) return;
  const targetNode = searchResults[index];
  centerNode(targetNode);
  
  d3.select("#search-status").text(`${index + 1} of ${searchResults.length}`);

  const nodeSelection = container.selectAll("g.node")
    .filter(d => uniqueKey(d) === uniqueKey(targetNode));
  
  nodeSelection.select("rect")
    .transition().duration(200)
    .attr("stroke", "#ff8800") 
    .attr("stroke-width", 5)
    .transition().duration(800)
    .attr("stroke", "red")     
    .attr("stroke-width", 3);
}

// Outline all matching nodes in red
function highlightAllMatches() {
  clearHighlights(); 
  
  const matchKeys = new Set(searchResults.map(uniqueKey));
  
  container.selectAll("g.node")
    .filter(d => matchKeys.has(uniqueKey(d)))
    .select("rect")
    .attr("stroke", "red")
    .attr("stroke-width", 3)
    .classed("search-match", true); 
}

// Clear highlights
function clearHighlights() {
  container.selectAll("g.node")
    .select("rect")
    .attr("stroke", "#333")
    .attr("stroke-width", 1)
    .classed("search-match", false);
}

function resetSearch() {
  // Clear state variables
  lastSearchTerm = "";
  searchResults = [];
  currentSearchIndex = 0;

  // UI Reset
  d3.select("#search-input").property("value", "");
  d3.select("#search-status").text("");
  clearHighlights();

  // Recursive collapse to return to default state
  function restoreAndCollapse(d) {
    // If it was expanded by search, move children back to _children
    if (d.children) {
      if (!d._children) d._children = [];
      // Merge if necessary
      d._children = d.children;
      d.children = null;
    }
    if (d._children) {
      d._children.forEach(restoreAndCollapse);
    }
  }

  // Sets root's immediate children visible
  if (root.children) {
    root.children.forEach(restoreAndCollapse);
  } else if (root._children) {
    root._children.forEach(restoreAndCollapse);
  }
  
  // Open first level by default (this can be removed if we want first level collapsed)
  if (root._children) {
    root.children = root._children;
    root._children = null;
  }

  // Re-render and center on home node
  update(root);
  centerNode(root);
}

// Reset the tree after searching by reloading the original data and reseting the view
function resetTree() {
  // Clear search state
  lastSearchTerm = "";
  searchResults = [];
  currentSearchIndex = 0;
  
  // Clear UI
  d3.select("#search-input").property("value", "");
  d3.select("#search-status").text("");
  clearHighlights();

  // Re-build the hierarchy from the original data
  // This ensures all nodes (including top-level ones) are restored
  if (root && root.data) {
    const originalData = root.data; 
    root = d3.hierarchy(originalData, childAccessor);
    root.x0 = 0; 
    root.y0 = 0;

    // Go to default state: Collapse everything except the first level
    if (root.children) {
      root.children.forEach(collapseAll);
    }
  }

  // Re-render and center on home node
  update(root);
  centerNode(root);
}

// Event listeners for search function

d3.select("#search-btn").on("click", () => {
  const term = d3.select("#search-input").property("value");
  searchNode(term);
});

d3.select("#search-input").on("keypress", (event) => {
  if (event.key === "Enter") {
    const term = d3.select("#search-input").property("value");
    searchNode(term);
  }
});

d3.select("#clear-btn").on("click", resetTree);


d3.select("#search-input").on("input", function() {
  if (!this.value.trim()) {
    resetTree();
  }
});

// Clear search when the input is emptied and reset the tree
d3.select("#search-input").on("input", function() {
  if (!this.value.trim()) {
    clearHighlights();
    d3.select("#search-status").text("");
    lastSearchTerm = "";
    searchResults = [];
    
    // Reset the tree to its default state (root visible, everything else collapsed)
    if (root.children) root.children.forEach(collapseAll);
    if (root._children) {
        root.children = root._children;
        root._children = null;
        root.children.forEach(collapseAll);
    }
    update(root);
    centerNode(root);
  }
});

