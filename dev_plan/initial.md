# VLSI Design Hierarchy Visualization Tool — Development Plan

## 1. Project Background

In VLSI design, gate-level netlists contain multi-level nested hierarchy structures. Each hierarchy exhibits distinct statistical characteristics in terms of data metrics. A visualization tool is therefore required to present the statistical data of each hierarchy level in a tabular form, enabling physical design engineers to rapidly analyze design-related data.

## 2. Project Development Requirements

Develop a graphical visualization tool that constructs the design hierarchy structure by reading `instance_info.json` and `cell_info.json`. Users shall be able to expand or collapse each hierarchy level starting from the top design node, with the corresponding metrics of each hierarchy displayed.

## 3. Input Files

### 3.1 `instance_info.json`

The data structure uses `leaf_instance_name` as the key. The instance naming convention follows a full hierarchical path, e.g., `"TOP/MACROA/UNIT1/inv_x"`. The parent-child relationship shall be constructed by splitting the path with `/`. The instance-related attributes are stored as a dictionary of values. Attributes include:

- `cell_name` (str)
- `dynamic_power` (float)
- `leakage_power` (float)
- `orient` (str)
- `location_x` (float)
- `location_y` (float)
- `is_physical_only` (bool)

The tool shall dynamically construct the hierarchy structure based on the input leaf instance names.

### 3.2 `cell_info.json`

The data structure uses `cell_name` as the key, with standard cell or macro-related attributes stored as a dictionary of values. Attributes include:

- `area` (float)
- `size_x` (float)
- `size_y` (float)
- `is_combinational_cell` (bool)
- `is_pulse_latch` (bool)
- `is_register_cell` (bool)
- `register_bit_count` (int)
- `drive_size` (int)
- `is_SVT` (bool)
- `is_LVT` (bool)
- `is_ULVT` (bool)
- `is_sram` (bool)
- `is_macro` (bool)
- `is_buffer` (bool)
- `is_inverter` (bool)
- `is_clock_cell` (bool)
- `is_integrated_clock_gating_cell` (bool)

### 3.3 Reserved Attributes and Exception Handling

Some of the above attributes are not currently utilized and are reserved for the subsequent 2D heat map feature. When an instance's `cell_name` has no matching entry in `cell_info.json`, it shall be flagged as an empty hierarchy, and a warning log shall be emitted.

## 4. Hierarchy Metrics

The following metrics are included. By default, the statistics cover standard cells that are non-macro and have `is_physical_only` set to `false`. Macro-related statistics are excluded unless explicitly specified. The default aggregation mode is hierarchy-flatten, covering all instances beneath the given hierarchy level:

1. **Area** — Total area of all instances.
2. **Count** — Total number of instances.
3. **ULVT Ratio** — Ratio of ULVT area to total area (`ULVT_area / total_area`).
4. **MB (Multi-Bit) Ratio** — Ratio of register bits belonging to multi-bit registers (where `register_bit_count > 1`) to the total register bit count.
5. **D1D2 Ratio** — Proportion of instances with `drive_size <= 2`.
6. **Buffer & Inverter Count** — Number of buffer and inverter instances.
7. **Buffer & Inverter Area** — Total area of buffer and inverter instances.

## 5. Technology Stack

- **Development Language:** Python 3.9
- **GUI Framework:** PyQt5
- **Data Structures & Computation:** pandas, numpy, scipy, and other high-performance libraries
- **Development Environment:** Windows 11 PC, 8 GB RAM, supporting up to 100k instances
- **Deployment Environment:** Linux, 100 GB RAM, supporting up to 20 million instances

## 6. Development Philosophy

### 6.1 Lightweight Frontend GUI

The visualization tree contains only hierarchies, not leaf instances. The total number of hierarchies is approximately 1/100 of the instance count. Under typical usage, users open at most the first 10 hierarchy levels for analysis. The following features are supported:

- Sorting by metric data
- Hierarchy name search
- `hier_min_inst_count_threshold` mechanism: After data preprocessing is complete, hierarchies with instance counts below this threshold are not displayed in the hierarchy tree. This filters out a large number of small hierarchies. This feature does not affect data accuracy; it only affects UI interaction.

### 6.2 High-Performance Backend

The backend must support data processing for up to 20 million instances. Although the number of hierarchies is typically far smaller than this value, the following mechanisms for handling large-scale instance preprocessing, intermediate data output, and rapid state recovery must be reflected throughout the development process. For example, after data preprocessing, the database is persisted via `pickle` to enable rapid data recovery on subsequent runs.

## 7. Feature Details

### 7.1 GUI Hierarchy Tree

Upon initialization, the tree displays the top-level hierarchy along with its first-level child hierarchies expanded. When a hierarchy is expanded, the parent-child hierarchical relationship must be clearly reflected in the graphical interface.

### 7.2 Data Search

Supports exact match, wildcard match, and regular expression match. After the search is completed, all matching hierarchies along with their metric data are listed in the search results window. The user may click to select a specific hierarchy, and the hierarchy tree will automatically expand to the selected hierarchy.

### 7.3 Data Sorting

Sorting can be performed by clicking on the metric column headers. Sorting is performed at the same hierarchy level only; cross-level sorting is not supported. For performance considerations, collapsed (un-expanded) hierarchies do not participate in sorting.

### 7.4 Two-Version Data Comparison

Supports loading two versions of data for side-by-side comparison. For each metric, both the absolute difference and the relative difference ratio shall be computed and displayed. Sorting by these difference values is also supported.
