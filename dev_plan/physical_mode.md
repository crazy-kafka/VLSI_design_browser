# Physical Mode for Design Browser
In phsycial mode, VLSI design browser use physical information like orient and location of instance with size of cell to build 2D array which will be rendered as heat map for visualize.
2D array means the grids to cut design in equal sqaure, default grid size is 3.0

# Layout view
Layout view will be created on the right side of main window.
Use QGraphicsView, QGraphicsPixmapItem and other necassary QT items to build layout view.
Layout view are fully interactive for user like pan, zoom, fit and etc.
Layout view generation should always include both standard cell type and marco type.
Each type of layout view use heat map to display 2D array; The heat gradient range has default value for different types, and also provide way to change range by user; show legend on the top right side of it.

# new data type for instance_info.json
Now add new data type: "boundary", which define block boundary with rectilinear coordinate (if only provided two points, transform it as four points rectangle)
When detect 'boundary' input, check legality of coordinates, it must be rectilinear shape. 
{
    'top_name': 'xxx',
    'instances': {},
    'boundary': [(x0, y0), (x1, y1), (x2, y2), (x3, y3)]
}

# cooridnate and orientation process for nested hierarchy layout build
For nested hierarchy, all instances under sub-blocks have to be processed by their orientation and coordinate. 
The coordinate attribute of instance info will be provided as DEF(Design exchange format) style.
There is a file named coorinateProcess.py under vlsi_viewer directory, which has orient and cooridinate processing function. Use it to deal with nested hierarchy scenario.

# Layout view type
1. Cell density map: In each grid, the density is calculated as (area of instances overlapped with this grid)/grid_area. Default range 0.0 ~ 1.0
2. Leakage power map: In each grid, the total power is calculated as accumulate of (instance_area_ratio_inside_this_grid * instance_leakage_power), Default range 0.0 ~ max value
3. Dynamic power map: Same as leakage power map, but use dynamic power.

# CLI change
Add new arguments --physical_mode to trigger this new feature.

# do not need to support compare mode support
Currently, physical mode do not support compare mode, --compare_block_info and --physical_mode are mutaully exclusive

# test plan
Create testing with high coverage of different scenarios. Create input files in sample_data for this new feature which is close to real design(multi level nested, rect-polygon shape, various orient, more than 100k instances totally) 
