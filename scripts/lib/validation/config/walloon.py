# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""Walloon-specific local input configuration."""

from pydantic import Field

from scripts.lib.validation.config._base import ConfigModel


class WalloonConfig(ConfigModel):
    """Configuration for local curated inputs used by the Walloon workflow."""

    be_regions_file: str = Field(
        "data/walloon/be.json",
        description="GeoJSON/JSON file defining the Belgium 3-region split used for Walloon clustering and plant reassignment.",
    )
    existing_capacities_file: str = Field(
        "data/walloon/wal_2021_existing_capacities_2.csv",
        description="Custom Belgium/Walloon existing generator list used to build the custom powerplant table.",
    )
    ntc_file: str = Field(
        "data/walloon/ntc_2030.csv",
        description="NTC input data used when `electricity.apply_ntc_constraints` is enabled.",
    )
