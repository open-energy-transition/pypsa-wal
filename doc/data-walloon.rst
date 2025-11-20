Walloon-specific Data
=====================

* ``data/walloon/custom_costs_rc.csv`` – custom cost assumptions used by the Walloon configuration. Data provided by ICEDD.
* ``data/walloon/custom_powerplants_add.csv`` - this is mainly BEVLG and BEBRU power plants (taken from a baseline `powerplants_s_adm.csv`),
  as well as some dummy nuclear links, to allow for new nuclear capacity expansion for the links.
* ``data/walloon/wal_2021_existing_capacities_2.csv`` - this contains data on existing generators in Wallonia; data provided by ICEDD.
* ``data/walloon/custom_powerplants_belgium.csv`` - this is the custom powerplants file that is used the Walloon workflow. This file is created
   using `scripts/walloon_scripts/convert_wal_existing_capacities.py` -- which processes `data/walloon/wal_2021_existing_capacities_2.csv` into 
   the format required for `data/custom_powerplants.csv`, and combines it with `data/walloon/custom_powerplants_add.csv` to make sure all Belgian
   power plants, as well as dummy nuclear links for new nuclear capacity expansion, are accounted for.
* ``data/custom_powerplants.csv`` – custom power plant modified to include the Walloon (BEWAL) nuclear power plant Tihange as 3 separate units for incremental retirement. Retirement data provided by ICEDD.
* ``data/walloon/custom_potentials.csv`` - custom potentials for the BEWAL region:
  - solid biomass import: maximum amount of biomass that can be imported to BEWAL from outside of the model area (non-Europe) (GWh/an)
  - solid biomass transported: maximum amount of biomass that can be transported from other nodes in the model to BEWAL (GWh/an)
  - solid biomass: maximum amount of local production of solid biomass in BEWAL region (GWh/an)
  - onwind, solar, solar rooftop: maximum potentials for onshore wind, solar PV and rooftop solar PV in BEWAL region (MW)
