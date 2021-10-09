MAXIMUM_TURNS = 360


class UnitTracker:
    def __init__(self, unit_id, city_id, destination):
        self.unit_id = unit_id
        self.city_id = city_id
        self.destination = destination

    def __str__(self):
        return f"Unit: {self.unit_id}, Destination: {self.destination}"

    def unit_has_work(self):
        if self.destination is not None:
            return True

        return False
