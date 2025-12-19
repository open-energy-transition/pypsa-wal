Walloon Specific Changes
========================

The Walloon workflow includes several changes to the default PyPSA-Eur:

* **Nuclear capacity expansion**: The `electricity.extendable_nuclear_links` is added to the 
  Walloon configuration in ``config/config.walloon.yaml`` to allow new nuclear capacity 
  to be built as extendable links, for the nodes and horizons specified. Additionally, 
  planned nuclear power plants can be added to ``data/custom_powerplants.csv``. 
* **Custom potentials for BEWAL.** The Walloon configuration uses custom potentials 
  for various energy resources, defined in  ``data/walloon/custom_potentials.csv``. 
  These potentials set maximum limits for solid biomass (imported, transported, and local production)
  in terms of annual energy (GWh/an). There are also maximum potentials for onshore wind, solar PV, 
  and rooftop solar PV in the BEWAL region, defined in MW. These custom potentials are activated
  via the `electricity.walloon_potentials` parameter in the Walloon configuration 
  ``config/config.walloon.yaml``.
* **Custom cost data.** The Walloon configuration uses updated cost assumptions 
  for specified fuels and technologies. These custom values are provided in 
  ``data/walloon/custom_costs_rc.csv`` and activated via the `costs.custom_cost_fn` 
  parameter in the Walloon configuration ``config/config.walloon.yaml``. 
* **Custom power plants retirements.** The Walloon (BEWAL) nuclear power plant, Tihange, 
  is now defined in ``data/custom_powerplants.csv`` with as 3 separate units
  (Tihange 1/2/3) to allow the plant to retire its capacity incrementally. 
  The workflow filters out those rows by the current planning horizon so a unit 
  automatically disappears once its retirement year is passed. 
* **Nuclear retrofit limit.** The ``electricity.retrofit_nuclear_once`` config option limits nuclear retrofits 
  to a single occurrence across horizons to avoid repeated retrofits.
* **Single nuclear representation.** Removed duplication of nuclear representation in 
  model -- before they were represented as both generators and links, now only as links.
* **No new BEWAL nuclear before 2040 and configurable new builds.** ``config/config.walloon.yaml`` 
  contains a Walloon override under ``electricity.extendable_carriers`` that allows nuclear to be
  extendable only for specific planning horizons (e.g. 2040 and 2050). The planning horizon and 
  the carrier list can be configured as needed.

With these adjustments the Walloon run retires the Tihange power plant incrementally 
at their scheduled dates, removes duplicate representation of nuclear, and only allows
new Belgian nuclear capacity when the config explicitly enables it.
