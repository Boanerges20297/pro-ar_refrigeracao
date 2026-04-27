import unicodedata

def remove_accents(input_str):
    if input_str is None:
        return None
    # Normalize to NFD to separate characters from their accents
    nfd_form = unicodedata.normalize('NFD', str(input_str))
    # Filter out characters in the 'Mn' (Mark, Nonspacing) category
    return "".join([c for c in nfd_form if unicodedata.category(c) != 'Mn']).lower()
