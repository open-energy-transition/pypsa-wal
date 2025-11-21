Walloon-specific Data
=====================

* ``data/walloon/custom_costs_rc.csv`` – custom cost assumptions used by the Walloon configuration. Data provided by ICEDD.
* ``data/walloon/wal_2021_existing_capacities_2.csv`` - this contains data on existing generators in Wallonia; data provided by ICEDD.
* ``data/custom_powerplants.csv`` – custom power plant modified to include the Walloon (BEWAL) nuclear power plant Tihange as 3 
   separate units for incremental retirement. Doel nuclear power plant in Flanders is also split into multiple generators for incremental
   retirement. Retirement data provided by ICEDD.
* ``data/walloon/custom_potentials.csv`` - custom potentials for the BEWAL region:
  - solid biomass import: maximum amount of biomass that can be imported to BEWAL from outside of the model area (non-Europe) (GWh/an)
  - solid biomass transported: maximum amount of biomass that can be transported from other nodes in the model to BEWAL (GWh/an)
  - solid biomass: maximum amount of local production of solid biomass in BEWAL region (GWh/an)
  - onwind, solar, solar rooftop: maximum potentials for onshore wind, solar PV and rooftop solar PV in BEWAL region (MW)
* ``data/walloon/ntc_2030.csv`` – net transfer capacities (NTCs) between European countries in 2030 (MW).