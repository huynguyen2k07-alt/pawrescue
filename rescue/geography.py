from decimal import Decimal


DA_NANG_CENTER = (Decimal("16.054400"), Decimal("108.202200"))
DA_NANG_BOUNDS = {
    "south": Decimal("15.850000"),
    "west": Decimal("107.750000"),
    "north": Decimal("16.250000"),
    "east": Decimal("108.350000"),
}


def is_within_da_nang(latitude, longitude):
    if latitude is None or longitude is None:
        return False
    latitude = Decimal(str(latitude))
    longitude = Decimal(str(longitude))
    return (
        DA_NANG_BOUNDS["south"] <= latitude <= DA_NANG_BOUNDS["north"]
        and DA_NANG_BOUNDS["west"] <= longitude <= DA_NANG_BOUNDS["east"]
    )
