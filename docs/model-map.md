# Model map

One picture of what the converter actually produces: every field a mapping
rule targets, shown under the groups that hold it, with each top-level section
as its own block. <span class="map-key">Blue</span> marks a path the base
model does not have, so the map also shows how much of the converter's output
comes from the electron-microscopy extensions rather than from `schema.json`.

<!-- begin generated map: scripts/gen_model_map.py -->

```mermaid
flowchart LR
classDef gbase fill:#8a8a8a26,stroke:#5f6368,stroke-width:2px
classDef fbase fill:none,stroke:#8a8a8a,stroke-width:1.5px
classDef gext fill:#4a7fb588,stroke:#2f6fa8,stroke-width:2.5px
classDef fext fill:#4a7fb53a,stroke:#4a7fb5,stroke-width:2px
subgraph s0 [" "]
direction LR
n0["Instrument"]
n1("Name")
n2("Manufacturer")
n3("Model")
n4("ID")
n5("Type")
n6["Vacuum"]
n7("SystemVacuum")
n0-->n1
n0-->n2
n0-->n3
n0-->n4
n0-->n5
n0-->n6
n6-->n7
end
subgraph s1 [" "]
direction LR
n8["Software"]
n9["AcquisitionSoftware"]
n10("Version")
n11("Name")
n12("ApplicationID")
n13("Version")
n14["SoftwareModule"]
n15("Version")
n16("Name")
n8-->n9
n8-->n12
n8-->n13
n8-->n14
n9-->n10
n9-->n11
n14-->n15
n14-->n16
end
subgraph s2 [" "]
direction LR
n17["Acquisition"]
n18["Operator"]
n19("Name")
n20("StartDate")
n17-->n18
n17-->n20
n18-->n19
end
subgraph s3 [" "]
direction LR
n21["ElectronBeam"]
n22["WorkingDistance"]
n23("Value")
n24("Unit")
n25("Focus")
n26("Type")
n27("Mode")
n28["Current"]
n29("Value")
n30["Stigmator"]
n31("X")
n32("Y")
n33["Shift"]
n34("X")
n35("Y")
n36("SpotSize")
n37["SourceTilt"]
n38("X")
n39("Y")
n40["AccelerationVoltage"]
n41("Value")
n42("Unit")
n43["EmissionCurrent"]
n44("Value")
n45("Unit")
n46("SpotIndex")
n47["ConvergenceAngle"]
n48("Value")
n49["Defocus"]
n50("Value")
n51("HighVoltage")
n21-->n22
n21-->n25
n21-->n26
n21-->n27
n21-->n28
n21-->n30
n21-->n33
n21-->n36
n21-->n37
n21-->n40
n21-->n43
n21-->n46
n21-->n47
n21-->n49
n21-->n51
n22-->n23
n22-->n24
n28-->n29
n30-->n31
n30-->n32
n33-->n34
n33-->n35
n37-->n38
n37-->n39
n40-->n41
n40-->n42
n43-->n44
n43-->n45
n47-->n48
n49-->n50
end
subgraph s4 [" "]
direction LR
n52["Scan"]
n53["FieldOfView"]
n54["X"]
n55("Value")
n56("Unit")
n57["Y"]
n58("Value")
n59("Unit")
n60["FrameTime"]
n61("Value")
n62["Rotation"]
n63("Value")
n64("Unit")
n65["LineTime"]
n66("Value")
n67("LineIntegrationCount")
n68("Detector")
n52-->n53
n52-->n60
n52-->n62
n52-->n65
n52-->n67
n52-->n68
n53-->n54
n53-->n57
n54-->n55
n54-->n56
n57-->n58
n57-->n59
n60-->n61
n62-->n63
n62-->n64
n65-->n66
end
subgraph s5 [" "]
direction LR
n69["Detector"]
n70("Name")
n71("Configuration")
n72("ActiveConfiguration")
n69-->n70
n69-->n71
n69-->n72
end
subgraph s6 [" "]
direction LR
n73["Image"]
n74["Plane"]
n75("PixelDwellTime")
n76("PixelDwellTimeUnit")
n77["Pixels"]
n78("SizeX")
n79("SizeY")
n80("PhysicalSizeX")
n81("PhysicalSizeY")
n82("PhysicalSizeXUnit")
n83("PhysicalSizeYUnit")
n84("PixelType")
n85("AcquisitionDate")
n86("Name")
n87("Type")
n88["Corrections"]
n89("Contrast")
n90("Brightness")
n91("Gamma")
n92("BlackLevel")
n93("WhiteLevel")
n94["CropHint"]
n95("Left")
n96("Right")
n97("Top")
n98("Bottom")
n99("Channel")
n100("BinaryResult")
n73-->n74
n73-->n77
n73-->n85
n73-->n86
n73-->n87
n73-->n88
n73-->n94
n73-->n99
n73-->n100
n74-->n75
n74-->n76
n77-->n78
n77-->n79
n77-->n80
n77-->n81
n77-->n82
n77-->n83
n77-->n84
n88-->n89
n88-->n90
n88-->n91
n88-->n92
n88-->n93
n94-->n95
n94-->n96
n94-->n97
n94-->n98
end
subgraph s7 [" "]
direction LR
n101["SamplePositioning"]
n102["Stage"]
n103["Position"]
n104["X"]
n105("Value")
n106("Unit")
n107["Y"]
n108("Value")
n109("Unit")
n110["Z"]
n111("Value")
n112("Unit")
n113["M"]
n114("Unit")
n115("Value")
n116["Rotation"]
n117("Value")
n118("Unit")
n119["Tilt"]
n120("Value")
n121["Alpha"]
n122("Value")
n123["Beta"]
n124("Value")
n125("Unit")
n126["RawPosition"]
n127["M"]
n128("Unit")
n129("Value")
n130["Rot"]
n131("Unit")
n132("Value")
n133["Tilt"]
n134("Unit")
n135("Value")
n136["X"]
n137("Unit")
n138("Value")
n139["Y"]
n140("Unit")
n141("Value")
n142["Z"]
n143("Unit")
n144("Value")
n145["Bias"]
n146("BiasType")
n147("Mode")
n148("Volts")
n149["MultiStage"]
n150["SampleHeight"]
n151("Unit")
n152("Value")
n153["SampleRadius"]
n154("Unit")
n155("Value")
n101-->n102
n102-->n103
n102-->n116
n102-->n119
n102-->n126
n102-->n145
n102-->n149
n103-->n104
n103-->n107
n103-->n110
n103-->n113
n104-->n105
n104-->n106
n107-->n108
n107-->n109
n110-->n111
n110-->n112
n113-->n114
n113-->n115
n116-->n117
n116-->n118
n119-->n120
n119-->n121
n119-->n123
n119-->n125
n121-->n122
n123-->n124
n126-->n127
n126-->n130
n126-->n133
n126-->n136
n126-->n139
n126-->n142
n127-->n128
n127-->n129
n130-->n131
n130-->n132
n133-->n134
n133-->n135
n136-->n137
n136-->n138
n139-->n140
n139-->n141
n142-->n143
n142-->n144
n145-->n146
n145-->n147
n145-->n148
n149-->n150
n149-->n153
n150-->n151
n150-->n152
n153-->n154
n153-->n155
end
subgraph s8 [" "]
direction LR
n156["Magnification"]
n157["Objective"]
n158("CalibratedMagnification")
n159("ID")
n160("ImmersionType")
n161("LensNA")
n162("Magnification")
n156-->n157
n157-->n158
n157-->n159
n157-->n160
n157-->n161
n157-->n162
end
subgraph s9 [" "]
direction LR
n163["ElectronSource"]
n164("Type")
n163-->n164
end
subgraph s10 [" "]
direction LR
n165["ElectronOptics"]
n166["CameraLength"]
n167("Value")
n168("OperatingMode")
n169("OperatingSubMode")
n170("ProjectorMode")
n171("Apertures")
n165-->n166
n165-->n168
n165-->n169
n165-->n170
n165-->n171
n166-->n167
end
subgraph s11 [" "]
direction LR
n172["SamplePreparation"]
n173["SampleHolder"]
n174("Type")
n175("ID")
n176("Sample")
n177["MountingMedium"]
n178("RefractiveIndex")
n172-->n173
n172-->n176
n172-->n177
n173-->n174
n173-->n175
n177-->n178
end
subgraph s12 [" "]
direction LR
n179["Settings"]
n180("ObjectiveSettings")
n179-->n180
end
subgraph s13 [" "]
direction LR
n181("CustomProperties")
end
subgraph s14 [" "]
direction LR
n182("Operations")
end
subgraph s15 [" "]
direction LR
n183("Features")
end
s0~~~s1~~~s2~~~s3~~~s4~~~s5
s6~~~s7~~~s8~~~s9~~~s10~~~s11
s12~~~s13~~~s14~~~s15
class n0,n8,n9,n14,n69,n73,n74,n77,n101,n102,n156,n157,n172,n173,n177,n179 gbase
class n1,n4,n10,n11,n15,n16,n75,n76,n78,n79,n80,n81,n82,n83,n84,n85,n86,n99,n158,n159,n160,n161,n162,n174,n175,n176,n178,n180 fbase
class n6,n17,n18,n21,n22,n28,n30,n33,n37,n40,n43,n47,n49,n52,n53,n54,n57,n60,n62,n65,n88,n94,n103,n104,n107,n110,n113,n116,n119,n121,n123,n126,n127,n130,n133,n136,n139,n142,n145,n149,n150,n153,n163,n165,n166 gext
class n2,n3,n5,n7,n12,n13,n19,n20,n23,n24,n25,n26,n27,n29,n31,n32,n34,n35,n36,n38,n39,n41,n42,n44,n45,n46,n48,n50,n51,n55,n56,n58,n59,n61,n63,n64,n66,n67,n68,n70,n71,n72,n87,n89,n90,n91,n92,n93,n95,n96,n97,n98,n100,n105,n106,n108,n109,n111,n112,n114,n115,n117,n118,n120,n122,n124,n125,n128,n129,n131,n132,n134,n135,n137,n138,n140,n141,n143,n144,n146,n147,n148,n151,n152,n154,n155,n164,n167,n168,n169,n170,n171,n181,n182,n183 fext
```

The **137 fields** some rule in `mappings.json` targets — what the converter can actually fill in — with the groups above them, 184 boxes over 16 sections. Rounded boxes are the targeted fields themselves; square boxes are the groups holding them. <span class="map-key">Blue</span> is a path `schema.json` does not have: 102 of the 137 targets come from the electron-microscopy extensions.

The other fields of the model are not drawn — all 2006 cannot be named in one static picture, and a field no rule targets is not something the converter can produce yet. Use the [model browser](model.md) to see the model in full.

<!-- end generated map -->

## Keeping this page in sync

The map is generated from the packaged mappings and model files, so it cannot
disagree with them. After editing `mappings.json` or a model:

```bash
python scripts/gen_model_map.py
```

`tests/test_model_map.py` fails when the map is stale, so it cannot drift from
the packaged files unnoticed.
