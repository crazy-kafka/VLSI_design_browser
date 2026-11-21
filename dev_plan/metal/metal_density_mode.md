# metal density development
Besides json, def and verilog mode, add new mode named "metal" which support metal density heat map displaying in GUI.

## Background in VLSI design
In physical design, there are power net(usually defined in SPECIALNETS statement) and signal net(usually defined in NETS statement), both of them occupy routing resources which is defined as TRACKS statement.
It is important to analyze metal utilization to identify congested area where signal noise and DRC violation are likely to occur.
Routing layer: In tech lef, routing layers are defined with direction, spacing rule, width rule and other more complex rules.
NDR(non default rule): the default routing rule for signal net is 1W1S(1 default width and 1 default spacing), but for critical signal like clock tree, 2W2S or 2W3S will be used for less delay and crosstalk. 

## How to calculate metal density map
Slice whole in to grid just like density map, the default grid size is 10. In each grid, the value range from 0 ~ 1.0, which mean the routing utilization ratio in side it.
In a grid, there are routing tracks for each routing layers inside it. Metal density can be calculated by single layers or by random combination of different layers. For example, to analyze vertial and horizontal metal resource, M1 M3 M5 can be grouped to display a horizontal routing map, M2 M4 M6 can be grouped tp display a verital routing map, and if to analyze middle layer routing usage, M3 M4 can be grouped.
Two ways to calculate, we should make detailed discussion on below methods to choose proper one or implement all and make them selective by GUI interacting or even drop all of them and brainstorm a better one:
1. Inside grid, a shape of net will occupied certain space, and each net should follow spacing rule, so net shape should be expanded by spacing requirement and a net occupied area is sum of shape area and spacing region area. Then total area of all nets in grid is calculated, the ratio is sum_of_area / grid_area. Non default rule wire should be considered according to multipiler of width and spacing. This method is not optimal if some local routing inside grid, which may not represent true congestion level.
2. At grid boundary, for example in horizontal direction, left and right side occupy some routing tracks which is defined in TRACKS statement, total resources is sum of tracks cross two side. Then count how many net shapes cross it(Non default rule should also be considered). The ratio will be number_net_occupied_at_two_side / total_resources. 

## User interface
New mode "metal" followed by DEF file, macro lef files and tech lef file.
New GUI, hierarchy tree is not needed in this mode, also not contour calculation. Metal density heat map occupied main window, at the right side there is checkbox for each routing layer from bottom layer to top layer. User is able to choose which layers are displayed togather. 
During development planing, create GUI ASCII layout for review.

## Statbility and Testing
This feature should not impact existing function. DEF/LEF parser should be modified if any parsing bug fix or enhance is required for NDR/NET/SPECIALNET/TRACK/etc.
Create testcase in sample_data for metal mode. Metal scheme select 1P12M, M1 M3 M5 M7 M9 M11 for horizontal layer, M2 M4 M6 M8 M10 M12 for veritical layer. Testing should cover multiple DEF inputs.

