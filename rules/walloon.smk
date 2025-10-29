# SPDX-FileCopyrightText: Open Energy Transition gGmbH and contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

rule build_custom_BE_busmap:
    input:
        network=resources("networks/base_s.nc"),
        be_shapefile="data/walloon/be.json",
    output:
        resources("resources/base_s_adm.csv")
    log:
        logs("build_custom_BE_busmap.log"),
    resources:
        mem_mb=20000,
    benchmark:
        benchmarks("build_custom_BE_busmap")
    threads: 8
    conda:
        "../envs/environment.yaml"
    script:
        "../scripts/custom_busmap_for_BE.py"