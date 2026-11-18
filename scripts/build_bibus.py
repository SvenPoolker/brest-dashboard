"""Build bibus.json: upcoming departures at one Bibus stop, from the official GTFS timetable.

Run daily by .github/workflows/bibus.yml. Standard library only.
Usage: python scripts/build_bibus.py [output_path]
"""
import csv, datetime, io, json, sys, urllib.request, zipfile

GTFS_URL = "https://s3.eu-west-1.amazonaws.com/files.orchestra.ratpdev.com/networks/bibus/exports/medias.zip"
STOP_PREFIX = "JJAUR_T"      # Jean Jaurès tram platforms (JJAUR_TA, JJAUR_TR)
STOP_NAME = "Jean Jaurès"
DAYS_AHEAD = 21


def read(z, name):
    return list(csv.DictReader(io.TextIOWrapper(z.open(name), encoding="utf-8-sig")))


def main(out_path):
    req = urllib.request.Request(GTFS_URL, headers={"User-Agent": "home-dashboard"})
    data = urllib.request.urlopen(req, timeout=120).read()
    z = zipfile.ZipFile(io.BytesIO(data))

    routes = {r["route_id"]: r for r in read(z, "routes.txt")}
    trips = {r["trip_id"]: r for r in read(z, "trips.txt")}

    # which services run on which date
    services = {}
    for r in read(z, "calendar.txt"):
        services[r["service_id"]] = r
    exceptions = {}
    for r in read(z, "calendar_dates.txt"):
        exceptions.setdefault(r["date"], {})[r["service_id"]] = r["exception_type"]

    def runs(service_id, day):
        ds = day.strftime("%Y%m%d")
        ex = exceptions.get(ds, {}).get(service_id)
        if ex == "1":
            return True
        if ex == "2":
            return False
        c = services.get(service_id)
        if not c or not (c["start_date"] <= ds <= c["end_date"]):
            return False
        weekday = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][day.weekday()]
        return c[weekday] == "1"

    # departures at the stop: (service_id, minutes after service-day midnight, route, headsign, direction)
    deps = []
    for r in read(z, "stop_times.txt"):
        if not r["stop_id"].startswith(STOP_PREFIX):
            continue
        t = trips[r["trip_id"]]
        h, m, _ = r["departure_time"].split(":")
        deps.append((t["service_id"], int(h) * 60 + int(m), t["route_id"], t["trip_headsign"], int(t["direction_id"] or 0)))

    route_ids = sorted({d[2] for d in deps})
    headsigns = sorted({d[3] for d in deps})
    today = datetime.date.today() - datetime.timedelta(days=1)  # include yesterday for after-midnight trips
    days = {}
    for k in range(DAYS_AHEAD + 1):
        day = today + datetime.timedelta(days=k)
        rows = sorted(
            [d[1], route_ids.index(d[2]), headsigns.index(d[3]), d[4]]
            for d in deps if runs(d[0], day)
        )
        if rows:
            days[day.isoformat()] = rows

    out = {
        "stop": STOP_NAME,
        "generated": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"),
        "routes": [{"id": rid, "name": routes[rid]["route_short_name"], "color": "#" + (routes[rid]["route_color"] or "888888")} for rid in route_ids],
        "headsigns": headsigns,
        "days": days,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("wrote", out_path, "days:", len(days), "departures:", sum(len(v) for v in days.values()))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "bibus.json")
