Walloon Specific Changes
========================

BEWAL nuclear retirements and additions
----------------------------------------

Walloon-specific adjustments to nuclear representation are made. Mainly, they are:

* **Tihange power plant retirement staging.** Entries in ``data/walloon/custom_decommissioning.csv`` are
  divided into separate units (e.g. Tihange 1/2/3) so ``DateOut`` can reflect the
  staged shutdowns. ``build_powerplants`` now filters those rows per planning
  horizon, so once a unit’s retirement year is reached it is dropped from later runs.
* **Nuclear as links.** "nuclear" is removed from `pypsa_eur.Generator` so it won't be represented twice 
  (as generators and as links). This changes the representation of nuclear in the model 
  from generators to links.
* **No new BEWAL nuclear before 2040.** ``config/config.walloon.yaml`` keeps nuclear
  out of ``electricity.extendable_carriers`` and explicitly lists BE under
  ``electricity.powerplants_filter`` so no new Belgian reactors can be added until
  the desired horizon.

With these changes the Walloon run retires the Tihange blocks at their scheduled
dates, uses the correct link-based representation, and prevents nuclear additions 
until the 2040 horizon.
