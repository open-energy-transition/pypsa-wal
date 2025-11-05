# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

import logging
import pandas as pd

logger = logging.getLogger(__name__)

def custom_pp_partitioning(ppl, custom_partitioned_pp_path):
	"""
	powerplants in the custom csv list will replace their analog in the pm generated ppl.
	the custom pp csv can specify different parameters for seperate generators in a powerplant.
	e.g. used for decomissioning portions of a powerplant in stages

	the name(s) and fueltype(s) of the plant in the custom csv must be the same as in the ppl
	"""
	add_ppls = pd.read_csv(custom_partitioned_pp_path)

	# Identify which row to remove in the original ppl
	for name in add_ppls['Name'].unique():
		for fueltype in add_ppls['Fueltype'].unique():
			indices_to_drop = ppl[(ppl['Name'] == name) & (ppl['Fueltype'] == fueltype)].index
			if not len(indices_to_drop) == 1:
				logger.warning(
					f"found {len(indices_to_drop)} powerplants matching name/fueltype in the original powerplant list."
				)
			ppl.drop(indices_to_drop, inplace=True)

	# Add back the partitioned list of ppls
	return pd.concat(
		[ppl, add_ppls], sort=False, ignore_index=True, verify_integrity=True
	)

