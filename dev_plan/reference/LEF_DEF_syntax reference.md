```markdown
---
name: lef-def-syntax-reference
description: Query and reference LEF/DEF syntax for IC design. Use when users ask about LEF (Library Exchange Format) or DEF (Design Exchange Format) file structure, syntax rules, layer definitions, macro definitions, via rules, spacing rules, antenna rules, or any LEF/DEF-related language reference questions. Covers version 5.8 including LEF58_ advanced properties.
---

# LEF/DEF Syntax Quick Reference Guide

> Based on LEF/DEF 5.8 Language Reference (January 2023). Designed for fast lookup of syntax rules, statement definitions, and property usage.

---

## Table of Contents

- [LEF Syntax](#lef-syntax)
  - [File Structure](#lef-file-structure)
  - [General Rules](#lef-general-rules)
  - [Core Statements](#lef-core-statements)
  - [Layer Definitions](#lef-layer-definitions)
  - [Macro Definition](#lef-macro-definition)
  - [Via Definition](#lef-via-definition)
  - [ViaRule Definition](#lef-viarule-definition)
  - [Nondefault Rule](#lef-nondefault-rule)
  - [LEF58_ Advanced Properties](#lef58-advanced-properties)
- [DEF Syntax](#def-syntax)
  - [File Structure](#def-file-structure)
  - [General Rules](#def-general-rules)
  - [Core Statements](#def-core-statements)
- [Appendix](#appendix)

---

## LEF Syntax

### LEF File Structure

```
[VERSION 5.8 ;]
[BUSBITCHARS "delimiterPair" ;]
[DIVIDERCHAR "character" ;]
[UNITS ... END UNITS]
[MANUFACTURINGGRID value ;]
[USEMINSPACING OBS {ON|OFF} ;]
[CLEARANCEMEASURE {MAXXY|EUCLIDEAN} ;]
[PROPERTYDEFINITIONS ... END PROPERTYDEFINITIONS]
[FIXEDMASK ;]
[LAYER ... END layerName] ...
[MAXVIASTACK value [RANGE bottomLayer topLayer] ;]
[VIA ... END viaName] ...
[VIARULE ... END viaRuleName] ...
[VIARULE viaRuleName GENERATE ... END viaRuleName] ...
[NONDEFAULTRULE ... END ruleName] ...
[SITE ... END siteName] ...
[MACRO ... END macroName] ...
[BEGINEXT ... ENDEXT] ...
[END LIBRARY]
```

### LEF General Rules

| Rule | Description |
|------|-------------|
| Identifier length | Max 2,048 characters |
| Distance unit | Microns |
| Precision control | UNITS statement |
| Statement termination | Semicolon `;`, space required before it |
| Keywords | Case insensitive |
| Comments | `#` at beginning of line |

### LEF Core Statements

#### VERSION
```lef
VERSION 5.8 ;
```

#### BUSBITCHARS
```lef
BUSBITCHARS "[]" ;  -- default value
```

#### DIVIDERCHAR
```lef
DIVIDERCHAR "/" ;  -- default value
```

#### UNITS
```lef
UNITS
  [TIME NANOSECONDS convertFactor ;]
  [CAPACITANCE PICOFARADS convertFactor ;]
  [RESISTANCE OHMS convertFactor ;]
  [POWER MILLIWATTS convertFactor ;]
  [CURRENT MILLIAMPS convertFactor ;]
  [VOLTAGE VOLTS convertFactor ;]
  [DATABASE MICRONS LEFconvertFactor ;]  -- default 100
  [FREQUENCY MEGAHERTZ convertFactor ;]
END UNITS
```

> Supported DATABASE MICRONS values: 100, 200, 400, 800, 1000, 2000, 4000, 8000, 10000, 20000

#### MANUFACTURINGGRID
```lef
MANUFACTURINGGRID value ;
```

#### USEMINSPACING
```lef
USEMINSPACING OBS {ON | OFF} ;
-- OFF recommended for 130nm and below
```

#### CLEARANCEMEASURE
```lef
CLEARANCEMEASURE {MAXXY | EUCLIDEAN} ;
-- Default: EUCLIDEAN
```

#### FIXEDMASK
```lef
FIXEDMASK ;
-- Disallows mask shifting; must precede LAYER statements
```

#### MAXVIASTACK
```lef
MAXVIASTACK value [RANGE bottomLayer topLayer] ;
```

#### PROPERTYDEFINITIONS
```lef
PROPERTYDEFINITIONS
  [objectType propName propType [RANGE min max] [value | "stringValue"] ;] ...
END PROPERTYDEFINITIONS

-- objectType: LAYER | LIBRARY | MACRO | NONDEFAULTRULE | PIN | VIA | VIARULE
-- propType: INTEGER | REAL | STRING
```

### LEF Layer Definitions

#### Layer (Cut) - Cut Layer
```lef
LAYER layerName
  TYPE CUT ;
  [MASK maskNum ;]
  [SPACING cutSpacing
    [CENTERTOCENTER]
    [SAMENET]
    [LAYER secondLayerName [STACK]
    | ADJACENTCUTS {2|3|4} WITHIN cutWithin [EXCEPTSAMEPGNET]
    | PARALLELOVERLAP
    | AREA cutArea]
  ;] ...
  [SPACINGTABLE ORTHOGONAL
    {WITHIN cutWithin SPACING orthoSpacing} ... ;]
  [ARRAYSPACING [LONGARRAY] [WIDTH viaWidth] CUTSPACING cutSpacing
    {ARRAYCUTS arrayCuts SPACING arraySpacing} ... ;]
  [WIDTH minWidth ;]
  [ENCLOSURE [ABOVE|BELOW] overhang1 overhang2
    [WIDTH minWidth [EXCEPTEXTRACUT cutWithin]
    | LENGTH minLength] ;] ...
  [PREFERENCLOSURE [ABOVE|BELOW] overhang1 overhang2 [WIDTH minWidth] ;] ...
  [RESISTANCE resistancePerCut ;]
  [ANTENNAMODEL {OXIDE1|OXIDE2|...|OXIDE32} ;] ...
  [ANTENNAAREARATIO value ;] ...
  [ANTENNADIFFAREARATIO {value | PWL((d1 r1)(d2 r2)...)} ;] ...
  [ANTENNACUMAREARATIO value ;] ...
  [ANTENNACUMDIFFAREARATIO {value | PWL(...)} ;] ...
  [ANTENNAAREAFACTOR value [DIFFUSEONLY] ;] ...
  [ANTENNACUMROUTINGPLUSCUT ;]
  [ANTENNAGATEPLUSDIFF plusDiffFactor ;]
  [ANTENNAAREAMINUSDIFF minusDiffFactor ;]
  [PROPERTY LEF58_* "..."] ...
END layerName
```

#### Layer (Routing) - Routing Layer
```lef
LAYER layerName
  TYPE ROUTING ;
  [MASK maskNum ;]
  DIRECTION {HORIZONTAL | VERTICAL | DIAG45 | DIAG135} ;
  PITCH {distance | xDistance yDistance} ;
  [DIAGPITCH {distance | diag45Distance diag135Distance} ;]
  WIDTH defaultWidth ;
  [OFFSET {distance | xDistance yDistance} ;]
  [DIAGWIDTH diagWidth ;]
  [DIAGSPACING diagSpacing ;]
  [AREA minArea ;]
  [MINSIZE minWidth minLength [...] ;]
  [SPACING minSpacing
    [RANGE minWidth maxWidth
      [USELENGTHTHRESHOLD | INFLUENCE value [RANGE ...] | RANGE ...]
    | LENGTHTHRESHOLD maxLength [RANGE ...]
    | ENDOFLINE eolWidth WITHIN eolWithin
      [PARALLELEDGE parSpace WITHIN parWithin [TWOEDGES]]
    | SAMENET [PGONLY]
    | NOTCHLENGTH minNotchLength
    | ENDOFNOTCHWIDTH endOfNotchWidth NOTCHSPACING minNotchSpacing NOTCHLENGTH minNotchLength]
  ;] ...
  [SPACINGTABLE
    [PARALLELRUNLENGTH {length}... {WIDTH width {spacing}...}... ;]
    [INFLUENCE {WIDTH width WITHIN distance SPACING spacing}... ;]
    [TWOWIDTHS {WIDTH width [PRL runLength] {spacing}...}... ;]
  ]
  [WIREEXTENSION value ;]
  [MINIMUMCUT numCuts WIDTH width [WITHIN cutDistance]
    [FROMABOVE|FROMBELOW] [LENGTH length WITHIN distance] ;] ...
  [MAXWIDTH width ;]
  [MINWIDTH width ;]
  [MINSTEP minStepLength [...] ;]
  [MINENCLOSEDAREA area [WIDTH width] ;] ...
  [PROTRUSIONWIDTH width1 LENGTH length WIDTH width2 ;]
  [RESISTANCE RPERSQ value ;]
  [CAPACITANCE CPERSQDIST value ;]
  [HEIGHT distance ;]
  [THICKNESS distance ;]
  [EDGECAPACITANCE value ;]
  [MINIMUMDENSITY minDensity ;]
  [MAXIMUMDENSITY maxDensity ;]
  [DENSITYCHECKWINDOW windowLength windowWidth ;]
  [DENSITYCHECKSTEP stepValue ;]
  [FILLACTIVESPACING spacing ;]
  [ANTENNA* ...]  -- same as Cut layer
  [PROPERTY LEF58_* "..."] ...
END layerName
```

#### Layer (Masterslice/Overlap)
```lef
LAYER layerName
  TYPE {MASTERSLICE | OVERLAP} ;
  [MASK maskNum ;]
  [PROPERTY LEF58_TYPE "TYPE [NWELL|PWELL|DIFFUSION|TRIMMETAL|REGION|...]" ;]
  [PROPERTY LEF58_* "..."] ...
END layerName
```

#### Layer (Implant)
```lef
LAYER layerName
  TYPE IMPLANT ;
  [MASK maskNum ;]
  [WIDTH minWidth ;]
  [SPACING minSpacing [LAYER layerName2] ;] ...
  [PROPERTY LEF58_* "..."] ...
END layerName
```

### LEF Macro Definition

```lef
MACRO macroName
  [CLASS {COVER [BUMP] | RING | BLOCK [BLACKBOX|SOFT]
    | PAD [INPUT|OUTPUT|INOUT|POWER|SPACER|AREAIO]
    | CORE [FEEDTHRU|TIEHIGH|TIELOW|SPACER|ANTENNACELL|WELLTAP]
    | ENDCAP {PRE|POST|TOPLEFT|TOPRIGHT|BOTTOMLEFT|BOTTOMRIGHT}} ;]
  [FIXEDMASK ;]
  [FOREIGN foreignCellName [pt [orient]] ;] ...
  [ORIGIN pt ;]
  [EEQ macroName ;]
  [SIZE width BY height ;]
  [SYMMETRY {X | Y | R90} ... ;]
  [SITE siteName [sitePattern] ;] ...
  [PIN pinName
    [TAPERRULE ruleName ;]
    [DIRECTION {INPUT|OUTPUT[TRISTATE]|INOUT|FEEDTHRU} ;]
    [USE {SIGNAL|ANALOG|POWER|GROUND|CLOCK} ;]
    [NETEXPR "netExprPropName defaultNetName" ;]
    [SUPPLYSENSITIVITY powerPinName ;]
    [GROUNDSENSITIVITY groundPinName ;]
    [SHAPE {ABUTMENT|RING|FEEDTHRU} ;]
    [MUSTJOIN pinName ;]
    {PORT
      [CLASS {NONE|CORE|BUMP} ;]
      {layerGeometries} ...
    END} ...
    [ANTENNAPARTIALMETALAREA value [LAYER layerName] ;] ...
    [ANTENNADIFFAREA value [LAYER layerName] ;] ...
    [ANTENNAMODEL {OXIDE1|...} ;] ...
    [ANTENNAGATEAREA value [LAYER layerName] ;] ...
    [ANTENNAMAXAREACAR value LAYER layerName ;] ...
    [PROPERTY LEF58_* "..." ;] ...
  END pinName] ...
  [OBS
    {layerGeometries} ...
  END]
  [DENSITY
    {LAYER layerName ;
      {RECT x1 y1 x2 y2 densityValue ;} ...
    } ...
  END] ...
  [PROPERTY LEF58_* "..." ;] ...
END macroName
```

### LEF Via Definition

```lef
VIA viaName [DEFAULT]
  { VIARULE viaRuleName ;
    CUTSIZE xSize ySize ;
    LAYERS botMetalLayer cutLayer topMetalLayer ;
    CUTSPACING xCutSpacing yCutSpacing ;
    ENCLOSURE xBotEnc yBotEnc xTopEnc yTopEnc ;
    [ROWCOL numCutRows numCutCols ;]
    [ORIGIN xOffset yOffset ;]
    [OFFSET xBotOffset yBotOffset xTopOffset yTopOffset ;]
    [PATTERN cutPattern ;]
  }
  | {[RESISTANCE resistValue ;]
    {LAYER layerName ;
      { RECT [MASK maskNum] pt pt ;
      | POLYGON [MASK maskNum] pt pt pt ... ;} ...
    } ...
  }
  [PROPERTY propName propVal ;] ...
END viaName
```

### LEF ViaRule Definition

```lef
-- Fixed ViaRule
VIARULE viaRuleName
  LAYER layerName ;
  DIRECTION {HORIZONTAL|VERTICAL} ;
  [WIDTH minWidth TO maxWidth ;]
  LAYER layerName ;
  DIRECTION {HORIZONTAL|VERTICAL} ;
  [WIDTH minWidth TO maxWidth ;]
  {VIA viaName ;} ...
  [PROPERTY propName propVal ;] ...
END viaRuleName

-- Generated ViaRule
VIARULE viaRuleName GENERATE [DEFAULT]
  LAYER routingLayerName ;
  ENCLOSURE overhang1 overhang2 ;
  [WIDTH minWidth TO maxWidth ;]
  LAYER routingLayerName ;
  ENCLOSURE overhang1 overhang2 ;
  [WIDTH minWidth TO maxWidth ;]
  LAYER cutLayerName ;
  RECT pt pt ;
  SPACING xSpacing BY ySpacing ;
  [RESISTANCE resistancePerCut ;]
END viaRuleName
```

### LEF Nondefault Rule

```lef
NONDEFAULTRULE ruleName
  [HARDSPACING ;]
  {LAYER layerName
    WIDTH width ;
    [DIAGWIDTH diagWidth ;]
    [SPACING minSpacing ;]
    [WIREEXTENSION value ;]
  END layerName} ...
  [VIA viaStatement] ...
  [USEVIA viaName ;] ...
  [USEVIARULE viaRuleName ;] ...
  [MINCUTS cutLayerName numCuts ;] ...
  [PROPERTY propName propValue ;] ...
  [PROPERTY LEF58_USEVIACUTCLASS "..."] ;
END ruleName
```

### LEF58_ Advanced Properties

#### Library-Level Properties (defined in PROPERTYDEFINITIONS)

| Property | Purpose |
|----------|---------|
| LEF58_ANTENNAMAXCUMAREA | Antenna max cumulative area rule |
| LEF58_ANTENNAMAXGATEAREA | Antenna max gate area rule |
| LEF58_ANTENNAMODELGROUP | Antenna model group rule |
| LEF58_CELLEDGESPACINGTABLE | Cell edge spacing table rule |
| LEF58_CELLVARIANTS | Cell variants rule |
| LEF58_CONSTRAINTLENGTH | Constraint length rule |
| LEF58_FINFET | FinFET rule |
| LEF58_LAYERMASKSHIFT | Layer mask shift rule |
| LEF58_MAXFLOATINGAREA | Max floating area rule |
| LEF58_MAXVIASTACK | Max via stack rule |
| LEF58_METALWIDTHTRACK | Metal width track rule |
| LEF58_METALWIDTHVIAMAP | Metal width via map rule |
| LEF58_PGVIATRACK | PG via track rule |
| LEF58_STACKVIALAYERRULE | Stack via layer rule |
| LEF58_STACKVIARULE | Stack via rule |
| LEF58_TAPDISTANCE | Tap distance rule |
| LEF58_TRIMMETALTRACK | Trim metal track rule |

#### Key Cut Layer LEF58_ Properties

| Property | Purpose |
|----------|---------|
| LEF58_TYPE | Layer type classification (TSV, MIMCAP, PASSIVATION, etc.) |
| LEF58_CUTCLASS | Via cut class definition |
| LEF58_SPACING | Advanced spacing rules |
| LEF58_SPACINGTABLE | Spacing table rules |
| LEF58_ENCLOSURE | Advanced enclosure rules |
| LEF58_ENCLOSURETABLE | Enclosure table rules |
| LEF58_ARRAYSPACING | Array spacing rules |
| LEF58_KEEPOUTZONE | Keep-out zone rules |
| LEF58_FORBIDDENSPACING | Forbidden spacing rules |
| LEF58_VIAGROUP | Via group rules |
| LEF58_VIACLUSTER | Via cluster rules |

#### Key Routing Layer LEF58_ Properties

| Property | Purpose |
|----------|---------|
| LEF58_TYPE | Layer type (POLYROUTING, MIMCAP, HIGHR, etc.) |
| LEF58_SPACING | Advanced spacing (EOL, CONVEXCORNERS, etc.) |
| LEF58_SPACINGTABLE | Advanced spacing tables |
| LEF58_EOLKEEPOUT | EOL keep-out rules |
| LEF58_AREA | Advanced area rules |
| LEF58_WIDTH | Width rules (incl. WRONGDIRECTION) |
| LEF58_WIDTHTABLE | Width table rules |
| LEF58_SPANLENGTHTABLE | Span length table rules |
| LEF58_MINIMUMCUT | Advanced minimum cut rules |
| LEF58_MINSTEP | Advanced min step rules |
| LEF58_FORBIDDENSPACING | Forbidden spacing rules |
| LEF58_CORNERSPACING | Corner spacing rules |
| LEF58_RIGHTWAYONGRIDONLY | Right way on grid only rule |
| LEF58_RECTONLY | Rectangle only rule |
| LEF58_EOLTRACK | EOL track rule |
| LEF58_PITCH | Pitch rule (incl. FIRSTLASTPITCH) |

---

## DEF Syntax

### DEF File Structure

```
[VERSION 5.8 ;]
[DIVIDERCHAR "/" ;]
[BUSBITCHARS "[]" ;]
DESIGN designName ;
[TECHNOLOGY technologyName ;]
[UNITS DISTANCE MICRONS dbuPerMicron ;]
[HISTORY ... ;] ...
[PROPERTYDEFINITIONS ... END PROPERTYDEFINITIONS]
[DIEAREA pt pt [pt] ... ;]
[ROW ... ;] ...
[TRACKS ... ;] ...
[GCELLGRID ... ;] ...
[VIAS ... END VIAS]
[STYLES ... END STYLES]
[NONDEFAULTRULES ... END NONDEFAULTRULES]
[REGIONS ... END REGIONS]
[COMPONENTMASKSHIFT ... ;]
[COMPONENTS ... END COMPONENTS]
[PINS ... END PINS]
[PINPROPERTIES ... END PINPROPERTIES]
[BLOCKAGES ... END BLOCKAGES]
[SLOTS ... END SLOTS]
[FILLS ... END FILLS]
[SPECIALNETS ... END SPECIALNETS]
[NETS ... END NETS]
[SCANCHAINS ... END SCANCHAINS]
[GROUPS ... END GROUPS]
[BEGINEXT ... ENDEXT] ...
END DESIGN
```

### DEF General Rules

| Rule | Description |
|------|-------------|
| Identifier length | Max 2,048 characters |
| Statement termination | Semicolon `;`, space required before it |
| Section definition | Each section defined once, ends with `END SECTION` |
| Coordinates | Integers, DEF database units |
| Default divider | `/` (DIVIDERCHAR) |
| Default busbit chars | `[]` (BUSBITCHARS) |
| Escape character | `\` |

### DEF Core Statements

#### DESIGN
```def
DESIGN designName ;
```

#### UNITS
```def
UNITS DISTANCE MICRONS dbuPerMicron ;
-- Must be an integer factor of LEF convertFactor
```

#### DIEAREA
```def
DIEAREA pt pt [pt] ... ;
-- Two points: rectangle; Multiple points: polygon (edges parallel to x/y axes)
```

#### ROW
```def
ROW rowName siteName origX origY siteOrient
  [DO numX BY numY [STEP stepX stepY]]
  [+ PROPERTY {propName propVal} ...] ... ;
```

#### TRACKS
```def
TRACKS
  [{X|Y} start DO numtracks STEP space
    [MASK maskNum [SAMEMASK]]
    [LAYER layerName ...]
  ;] ...
```

#### TRACKPROPERTIES (via PROPERTYDEFINITIONS)
```def
PROPERTYDEFINITIONS
  DESIGN TRACKPROPERTIES STRING "
    TRACKS [{X|Y} start DO numtracks STEP space
      [MASK maskNum [SAMEMASK]]
      [LAYER layerName ...]
      [WIDTH width]
      [NDR ruleName]]...
    ;..."
END PROPERTYDEFINITIONS
```

#### COMPONENTS
```def
COMPONENTS numComps ;
[- compName modelName
  [+ EEQMASTER macroName]
  [+ SOURCE {NETLIST|DIST|USER|TIMING}]
  [+ {FIXED pt orient | COVER pt orient | PLACED pt orient | UNPLACED}]
  [+ MASKSHIFT shiftLayerMasks]
  [+ HALO [SOFT] left bottom right top]
  [+ ROUTEHALO haloDist minLayer maxLayer]
  [+ WEIGHT weight]
  [+ REGION regionName]
  [+ PROPERTY {propName propVal} ...]
;] ...
END COMPONENTS
```

#### PINS
```def
PINS numPins ;
[- pinName + NET netName
  [+ SPECIAL]
  [+ DIRECTION {INPUT|OUTPUT|INOUT|FEEDTHRU}]
  [+ NETEXPR "netExprPropName defaultNetName"]
  [+ SUPPLYSENSITIVITY powerPinName]
  [+ GROUNDSENSITIVITY groundPinName]
  [+ USE {SIGNAL|POWER|GROUND|CLOCK|TIEOFF|ANALOG|SCAN|RESET}]
  [+ ANTENNA* ...]
  [[+ PORT]
    [+ LAYER layerName [MASK maskNum]
      [SPACING minSpacing | DESIGNRULEWIDTH effectiveWidth]
      pt pt
    |+ POLYGON layerName [MASK maskNum] [...] pt pt pt ...
    |+ VIA viaName [MASK viaMaskNum] pt]
    [+ COVER pt orient | FIXED pt orient | PLACED pt orient]
  ] ...
;] ...
END PINS
```

#### NETS
```def
NETS numNets ;
[- {netName
    [( {compName pinName | PIN pinName} [+ SYNTHESIZED] )] ...
  | MUSTJOIN ( compName pinName )}
  [+ SHIELDNET shieldNetName] ...
  [+ VPIN vpinName [LAYER layerName] pt pt [PLACED|FIXED|COVER pt orient]]
  [+ SUBNET subnetName [...] [NONDEFAULTRULE rulename] [regularWiring]]
  [+ XTALK class]
  [+ NONDEFAULTRULE ruleName]
  [regularWiring]
  [+ SOURCE {DIST|NETLIST|TEST|TIMING|USER}]
  [+ FIXEDBUMP]
  [+ FREQUENCY frequency]
  [+ ORIGINAL netName]
  [+ USE {ANALOG|CLOCK|GROUND|POWER|RESET|SCAN|SIGNAL|TIEOFF}]
  [+ PATTERN {BALANCED|STEINER|TRUNK|WIREDLOGIC}]
  [+ ESTCAP wireCapacitance]
  [+ WEIGHT weight]
  [+ PROPERTY {propName propVal} ...]
;] ...
END NETS
```

#### Regular Wiring Syntax
```def
{+ COVER | + FIXED | + ROUTED | + NOSHIELD}
layerName [TAPER | TAPERRULE ruleName] [STYLE styleNum]
routingPoints
[NEW layerName [TAPER | TAPERRULE ruleName] [STYLE styleNum]
 routingPoints] ...

-- routingPoints syntax:
{ ( x y [extValue] )
  {[MASK maskNum] ( x y [extValue] )
  |[MASK viaMaskNum] viaName [orient]
  |[MASK maskNum] RECT ( dx1 dy1 dx2 dy2 )
  | VIRTUAL ( x y ) } } ...
```

#### SPECIALNETS
```def
SPECIALNETS numNets ;
[- netName
  [( {compName pinName | PIN pinName} [+ SYNTHESIZED] )] ...
  [+ VOLTAGE volts]
  [specialWiring]
  [+ SOURCE ...]
  [+ FIXEDBUMP]
  [+ USE ...]
  [+ PATTERN ...]
  [+ WEIGHT weight]
  [+ PROPERTY {propName propVal} ...]
;] ...
END SPECIALNETS
```

#### Special Wiring Syntax
```def
[[+ COVER | + FIXED | + ROUTED | + SHIELD shieldNetName]
 [+ SHAPE shapeType] [+ MASK maskNum]
 + POLYGON layerName pt pt pt ...
 | + RECT layerName pt pt
 | + VIA viaName [orient] pt ...
 |{+ COVER | + FIXED | + ROUTED | + SHIELD shieldNetName}
   layerName routeWidth
   [+ SHAPE {RING|PADRING|BLOCKRING|STRIPE|FOLLOWPIN|...}]
   [+ STYLE styleNum]
   routingPoints
   [NEW layerName routeWidth [...] routingPoints]
] ...

-- shapeType: RING | PADRING | BLOCKRING | STRIPE | FOLLOWPIN |
--            IOWIRE | COREWIRE | BLOCKWIRE | BLOCKAGEWIRE |
--            FILLWIRE | FILLWIREOPC | DRCFILL

-- Via array syntax:
[DO numX BY numY STEP stepX stepY]
```

#### VIAS
```def
VIAS numVias ;
[- viaName
  [ + VIARULE viaRuleName
    + CUTSIZE xSize ySize
    + LAYERS botmetalLayer cutLayer topMetalLayer
    + CUTSPACING xCutSpacing yCutSpacing
    + ENCLOSURE xBotEnc yBotEnc xTopEnc yTopEnc
    [+ ROWCOL numCutRows NumCutCols]
    [+ ORIGIN xOffset yOffset]
    [+ OFFSET xBotOffset yBotOffset xTopOffset yTopOffset]
    [+ PATTERN cutPattern]
  ]
  | [ + RECT layerName [+ MASK maskNum] pt pt
    | + POLYGON layerName [+ MASK maskNum] pt pt pt] ...
;] ...
END VIAS
```

#### STYLES
```def
STYLES numStyles ;
{- STYLE styleNum pt pt ... ;} ...
END STYLES
-- styleNum starts from 0
-- Polygon must be convex, edges parallel to x/y axes or 45 degrees
-- Must enclose point (0 0)
```

#### NONDEFAULTRULES
```def
NONDEFAULTRULES numRules ;
{- ruleName
  [+ HARDSPACING]
  {+ LAYER layerName
    WIDTH minWidth
    [DIAGWIDTH diagWidth]
    [SPACING minSpacing]
    [WIREEXT wireExt]
  } ...
  [+ VIA viaName] ...
  [+ VIARULE viaRuleName] ...
  [+ MINCUTS cutLayerName numCuts] ...
  [+ PROPERTY {propName propVal} ...]
  [PROPERTY LEF58_USEVIACUTCLASS "..."]
;} ...
END NONDEFAULTRULES
```

#### BLOCKAGES
```def
BLOCKAGES numBlockages ;
[- LAYER layerName
  [+ COMPONENT compName | + SLOTS | + FILLS | + PUSHDOWN | + EXCEPTPGNET]
  [+ SPACING minSpacing | + DESIGNRULEWIDTH effectiveWidth]
  [+ MASK maskNum]
  {RECT pt pt | POLYGON pt pt pt ...} ...
;] ...
[- PLACEMENT
  [+ SOFT | + PARTIAL maxDensity]
  [+ PUSHDOWN]
  [+ COMPONENT compName
  {RECT pt pt} ...
;] ...
END BLOCKAGES
```

#### FILLS
```def
FILLS numFills ;
[- LAYER layerName [+ MASK maskNum] [+ OPC]
  {RECT pt pt | POLYGON pt pt pt ...} ...
;] ...
[- VIA viaName [+ MASK viaMaskNum] [+ OPC] pt ...
;] ...
END FILLS
```

#### COMPONENTMASKSHIFT
```def
COMPONENTMASKSHIFT layer1 [layer2 ...] ;
-- Layers listed from highest to lowest
-- shiftLayerMasks is hex-encoded, one digit per multi-mask layer
-- 2-mask: 0=no shift, 1=shift by 1
-- 3-mask: 0=none, 1=shift1, 2=shift2, 3=fix mask1 swap 2&3,
--         4=fix mask2 swap 1&3, 5=fix mask3 swap 1&2
```

#### SLOTS
```def
SLOTS numSlots ;
[- LAYER layerName
  {RECT pt pt | POLYGON pt pt pt ...} ...
;] ...
END SLOTS
```

#### REGIONS
```def
REGIONS numRegions ;
[- regionName {pt pt} ...
  [+ TYPE {FENCE | GUIDE}]
  [+ PROPERTY {propName propVal} ...]
;] ...
END REGIONS
```

#### GROUPS
```def
GROUPS numGroups ;
[- groupName [compNamePattern ...]
  [+ REGION regionName]
  [+ PROPERTY {propName propVal} ...]
;] ...
END GROUPS
```

#### SCANCHAINS
```def
SCANCHAINS numScanChains ;
[- chainName
  [+ PARTITION partitionName [MAXBITS maxbits]]
  [+ COMMONSCANPINS [( IN pin )] [( OUT pin )]]
  + START {fixedInComp | PIN} [outPin]
  [+ FLOATING
    {floatingComp [( IN pin )] [( OUT pin )] [( BITS numBits )]} ...]
  [+ ORDERED
    {fixedComp [( IN pin )] [( OUT pin )] [( BITS numBits )]} ...
  ] ...
  + STOP {fixedOutComp | PIN} [inPin]
;] ...
END SCANCHAINS
```

#### PINPROPERTIES
```def
PINPROPERTIES num;
[- {compName pinName | PIN pinName}
  [+ PROPERTY {propName propVal} ...]
;] ...
END PINPROPERTIES
```

---

## Appendix

### Orientation Mapping

| LEF/DEF | OpenAccess | Description |
|---------|------------|-------------|
| N | R0 | North (default) |
| S | R180 | South |
| W | R90 | West |
| E | R270 | East |
| FN | MY | Flipped North |
| FS | MX | Flipped South |
| FW | MX90 | Flipped West |
| FE | MY90 | Flipped East |

### Via Mask Encoding

`viaMaskNum` is a hex-encoded 3-digit value: `<topMaskNum><cutMaskNum><bottomMaskNum>`

- Example: `MASK 113` = top metal mask 1, cut layer mask 1, bottom metal mask 3
- `0` = no mask (uncolored)
- Missing digits default to 0: `013` = `13`

### LEF/DEF Unit Conversion

| SI Unit | Database Precision |
|---------|-------------------|
| 1 nanosecond | 1,000 DBUs |
| 1 picofarad | 1,000,000 DBUs |
| 1 ohm | 10,000 DBUs |
| 1 milliwatt | 10,000 DBUs |
| 1 milliamp | 10,000 DBUs |
| 1 volt | 1,000 DBUs |

### DEF Coordinate Conventions

- `( x * )` = use last y coordinate
- `( * y )` = use last x coordinate
- `( * * extValue )` = specify wire extension at via
- First coordinate cannot use `*`
- Subsequent points must form orthogonal paths

### Wire Extension Defaults

| Type | Default Extension |
|------|-------------------|
| NETS (regular wiring) | Half wire width |
| SPECIALNETS (special wiring) | 0 |
| Segments with STYLE | Extension value ignored |
| Diagonal segments | Extension value ignored |

### Key LEF58_ Property Quick Reference

#### Width-Related
- `LEF58_WIDTH` - Define default routing width, supports WRONGDIRECTION
- `LEF58_WIDTHTABLE` - Define all legal widths
- `LEF58_SPANLENGTHTABLE` - Define all legal span lengths

#### Spacing-Related
- `LEF58_SPACING` - Advanced spacing (EOL, SAMEMASK, WRONGDIRECTION, etc.)
- `LEF58_SPACINGTABLE` - Advanced spacing tables (TWOWIDTHS, DIRECTIONALSPANLENGTH, etc.)
- `LEF58_CORNERSPACING` - Corner spacing
- `LEF58_FORBIDDENSPACING` - Forbidden spacing

#### EOL-Related
- `LEF58_EOLKEEPOUT` - EOL keep-out zone
- `LEF58_EOLTRACK` - EOL track alignment
- `LEF58_EOLVIAKEEPOUT` - EOL via keep-out
- `LEF58_EOLEXTENSIONSPACING` - EOL extension spacing

#### Via-Related
- `LEF58_CUTCLASS` - Via cut class
- `LEF58_ENCLOSURE` - Advanced enclosure
- `LEF58_MINIMUMCUT` - Advanced minimum cut
- `LEF58_MAXVIASTACK` - Max via stack

#### Region-Related
- `LEF58_REGION` - Region-specific rules
- `LEF58_RECTONLY` - Rectangle only
- `LEF58_RIGHTWAYONGRIDONLY` - Right way on grid only

#### Antenna-Related
- `LEF58_ANTENNADIFFGATEPWL` - Antenna diff gate PWL
- `LEF58_ANTENNAGATEPWL` - Antenna gate PWL
- `LEF58_ANTENNAGATEPLUSDIFF` - Antenna gate plus diffusion
- `LEF58_ANTENNADIFFONLYAREARATIO` - Antenna diff only area ratio
- `LEF58_ANTENNADIFFPROTECTORAREARATIO` - Antenna diff protector area ratio
```