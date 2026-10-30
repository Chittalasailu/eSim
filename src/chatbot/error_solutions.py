# error_solutions.py
from typing import Dict, Any, List, Optional

ERROR_SOLUTIONS = {
    "no ground": {
        "description": "Missing ground reference (Node 0)",
        "severity": "critical",
        "fixes": [
            "Add GND symbol (0) to schematic",
            "Ensure all nodes have DC path to ground",
            "Add 1GΩ resistors from floating nodes to GND for simulation stability",
            "Use GND symbol from eSim power library"
        ],
        "eSim_command": "Add 'GND' symbol from 'power' library"
    },
    
    "floating pins": {
        "description": "Unconnected component pins",
        "severity": "moderate",
        "fixes": [
            "Connect all unused pins to appropriate nets",
            "For unused inputs: tie to VCC or GND through resistors",
            "For unused outputs: leave unconnected but label properly"
        ],
        "eSim_command": "Use 'Place Wire' tool to connect pins"
    },
    
    "disconnected wires": {
        "description": "Wires not properly connected to pins",
        "severity": "critical",
        "fixes": [
            "Zoom in and check wire endpoints touch pins",
            "Use junction dots at wire intersections",
            "Re-route wires to ensure proper connections"
        ],
        "eSim_command": "Press 'J' to add junction dots"
    },
    
    "missing spice model": {
        "description": "Component lacks SPICE model definition",
        "severity": "critical",
        "fixes": [
            "Add .lib statement: .lib /usr/share/esim/models.lib",
            "Check IC availability in Components/ICs.pdf",
            "Use eSim library components only",
            "Create custom model using Model Editor"
        ],
        "eSim_command": "Add '.lib /usr/share/esim/models.lib' in schematic"
    },
    
    "singular matrix": {
        "description": "Simulation convergence error",
        "severity": "critical",
        "fixes": [
            "Add 1GΩ resistors from ALL nodes → GND",
            "Add .options gmin=1e-12 reltol=0.01",
            "Use .nodeset for initial voltages",
            "Add 0.1Ω series resistors to voltage sources"
        ],
        "eSim_command": "Add '.options gmin=1e-12 reltol=0.01' in .cir file"
    },
    
    "missing component values": {
        "description": "Components without specified values",
        "severity": "moderate",
        "fixes": [
            "Double-click components to edit values",
            "Set R, C, L values before simulation",
            "For ICs: specify model number",
            "For sources: set voltage/current values"
        ],
        "eSim_command": "Double-click component → Edit Properties → Set Value"
    },
    
    "no load after rectifier": {
        "description": "Rectifier output has no load capacitor",
        "severity": "warning",
        "fixes": [
            "Add filter capacitor after rectifier (100-1000μF)",
            "Add load resistor to establish DC operating point",
            "Add voltage regulator for stable output"
        ],
        "eSim_command": "Add capacitor between rectifier output and GND"
    },

    # Keys below are the text ngspice itself prints, so they match real logs.
    "timestep too small": {
        "description": "Transient analysis cannot converge (ngspice: Timestep too small)",
        "severity": "critical",
        "fixes": [
            "Check the node ngspice names after 'trouble with node' for a missing or wrong connection",
            "Look for unrealistic values (0 Ω, very large capacitors or inductors) and ideal switches",
            "Add a small series resistance (e.g. 1 mΩ) to voltage sources and inductors",
            "Add '.options method=gear' or relax tolerances with '.options reltol=0.01'"
        ],
        "eSim_command": "Fix the circuit in the schematic, then run KiCad to Ngspice again"
    },

    "could not find a valid modelname": {
        "description": "A component's SPICE model is missing (ngspice: Could not find a valid modelname)",
        "severity": "critical",
        "fixes": [
            "Check that every diode, transistor and IC uses a part from the eSim libraries",
            "Make sure the model file for the part is selected in the converter",
            "Create or add the model with the Model Editor if eSim does not have it"
        ],
        "eSim_command": "KiCad to Ngspice → Device Modeling tab → select the model file"
    },

    "unknown subckt": {
        "description": "A subcircuit used in the schematic was not found (ngspice: unknown subckt)",
        "severity": "critical",
        "fixes": [
            "Select the subcircuit's folder for every X component in the converter",
            "Check the subcircuit name matches the one created in Subcircuit Builder",
            "Run KiCad to Ngspice again after changing the schematic"
        ],
        "eSim_command": "KiCad to Ngspice → Subcircuits tab → add the subcircuit"
    },

    "gmin stepping failed": {
        "description": "DC operating point did not converge (ngspice: gmin stepping failed)",
        "severity": "critical",
        "fixes": [
            "Check every node has a DC path to ground",
            "Look for floating gates/inputs and missing source values",
            "Add '.nodeset' initial voltages or '.options gmin=1e-12 reltol=0.01'"
        ],
        "eSim_command": "Add the .options/.nodeset line in the converter's Analysis tab or the .cir file"
    },

    "no such vector": {
        "description": "A plotted or printed node does not exist (ngspice: no such vector)",
        "severity": "moderate",
        "fixes": [
            "Check the node name in the plot/print command matches a net label in the schematic",
            "Add net labels to the nodes you want to plot and regenerate the netlist"
        ],
        "eSim_command": "Add a label in the schematic, then run KiCad to Ngspice again"
    }
}


def known_errors(log: str) -> List[Dict[str, Any]]:
    """Table entries whose key appears in `log`; no generic fallback."""
    text = (log or "").lower()
    return [solution for key, solution in ERROR_SOLUTIONS.items() if key in text]


def known_errors_text(log: str) -> str:
    """The known fixes for errors in `log` as plain text, or "" if none match."""
    parts = []
    for solution in known_errors(log):
        fixes = "\n".join(f"- {fix}" for fix in solution["fixes"])
        parts.append(f"{solution['description']}:\n{fixes}\n"
                     f"In eSim: {solution['eSim_command']}")
    return "\n\n".join(parts)


def get_error_solution(error_message: str) -> Optional[Dict[str, Any]]:
    """Get detailed solution for specific error (None when there is no text)."""
    if not error_message:
        return None
    error_lower = error_message.lower()
    
    for error_key, solution in ERROR_SOLUTIONS.items():
        if error_key in error_lower:
            return solution
    
    # Default solution for unknown errors
    return {
        "description": "General schematic error",
        "severity": "unknown",
        "fixes": [
            "Check all connections are proper",
            "Verify component values are set",
            "Ensure ground symbol is present",
            "Check for duplicate component IDs"
        ],
        "eSim_command": "Run Design Rule Check (DRC) in KiCad"
    }
