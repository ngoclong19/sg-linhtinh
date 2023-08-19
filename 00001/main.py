"""Main
"""

import fetchmb

if __name__ == "__main__":
    fetchmb.main(1990, r"^[a-z]{4}$", debug=True)
    fetchmb.main(1995, r"^the [a-z]{6}$", debug=True)
    fetchmb.main(1980, r"^a [a-z]{6}$", debug=True)
    fetchmb.main(
        1987, r"^[a-z]{3}'[a-z]{2} [a-z]{3} [a-z]{4}, g[a-z]{3}$", debug=True
    )
    fetchmb.main(1992, r"^d[a-z]{4} [a-z]{5}$", debug=True)
