# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

import logging
import pandas as pd

logger = logging.getLogger(__name__)

def overwrite_costs(costs, update_cost_fn):
    """
    Overwrite default cost data from ``technology-data``.

    Parameters
    ----------
    costs : pandas.DataFrame
        Original cost data, indexed by a MultiIndex with
        (technology, parameter).
    update_cost_fn : str or Path, optional
        Path to a CSV file containing updated cost values.
        The file is expected to have a MultiIndex on its rows
        (two columns used as index, e.g. technology and parameter).

    Returns
    -------
    pandas.DataFrame
        The `costs` object with updated values from the update file,
        if applicable.
    """

    if update_cost_fn is not None:
        costs_update = pd.read_csv(update_cost_fn, index_col=[0,1])

        logger.info(
            f"Overwriting parameters {costs_update.index.get_level_values(1)} "
            f"for technologies {costs_update.index.get_level_values(0)}."
        )

    costs.loc[costs_update.index] = costs_update
    
    return costs