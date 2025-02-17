from itertools import permutations

characters = "5d2eG"
giveaways = ["".join(p) for p in permutations(characters)]
