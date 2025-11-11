Walloon Specific Changes
========================

This branch adapts the Walloon configuration so Belgian nuclear units follow the
expected phase-out and build logic:

* **Custom power plants retirements.** The Walloon (BEWAL) nuclear power plant, Tihange, 
  is now defined in ``data/custom_powerplants.csv`` with as 3 separate units
  (Tihange 1/2/3) to allow the plant to retire its capacity incrementally. 
  The workflow filters out those rows by the current planning horizon so a unit 
  automatically disappears once its retirement year is passed. 
* **Single nuclear representation.** Removed duplication of nuclear representation in 
  model -- before they were represented as both generators and links, now only as links.
* **No new BEWAL nuclear before 2040 and configurable new builds.** ``config/config.walloon.yaml`` 
  contains a Walloon override under ``electricity.extendable_carriers`` that allows nuclear to be
  extendable only for specific planning horizons (e.g. 2040 and 2050). The planning horizon and 
  the carrier list can be configured as needed.

With these adjustments the Walloon run retires the Tihange power plant incrementally 
at their scheduled dates, removes duplicate representation of nuclear, and only allows
new Belgian nuclear capacity when the config explicitly enables it.
