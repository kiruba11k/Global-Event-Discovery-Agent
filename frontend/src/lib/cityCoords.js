/*
  cityCoords.js — lat/lng lookup for placing DB event locations on the
  hero globe. The DB stores city + country but no coordinates, so we
  match against ~90 major tradeshow cities, then fall back to the
  country's main hub. Unmatched locations simply don't render a marker.
*/

export const CITY_COORDS = {
  'las vegas': [36.17, -115.14], 'san francisco': [37.77, -122.42],
  'new york': [40.71, -74.01], 'chicago': [41.88, -87.63],
  'orlando': [28.54, -81.38], 'austin': [30.27, -97.74],
  'boston': [42.36, -71.06], 'los angeles': [34.05, -118.24],
  'toronto': [43.65, -79.38], 'vancouver': [49.28, -123.12],
  'mexico city': [19.43, -99.13], 'são paulo': [-23.55, -46.63],
  'sao paulo': [-23.55, -46.63], 'buenos aires': [-34.60, -58.38],
  'london': [51.51, -0.13], 'birmingham': [52.49, -1.89],
  'manchester': [53.48, -2.24], 'paris': [48.86, 2.35],
  'lyon': [45.76, 4.84], 'berlin': [52.52, 13.40],
  'munich': [48.14, 11.58], 'frankfurt': [50.11, 8.68],
  'cologne': [50.94, 6.96], 'düsseldorf': [51.23, 6.78],
  'dusseldorf': [51.23, 6.78], 'hannover': [52.37, 9.73],
  'hanover': [52.37, 9.73], 'hamburg': [53.55, 9.99],
  'nuremberg': [49.45, 11.08], 'stuttgart': [48.78, 9.18],
  'amsterdam': [52.37, 4.90], 'rotterdam': [51.92, 4.48],
  'brussels': [50.85, 4.35], 'barcelona': [41.38, 2.17],
  'madrid': [40.42, -3.70], 'lisbon': [38.72, -9.14],
  'milan': [45.46, 9.19], 'rome': [41.90, 12.50],
  'bologna': [44.49, 11.34], 'geneva': [46.20, 6.14],
  'zurich': [47.38, 8.54], 'vienna': [48.21, 16.37],
  'copenhagen': [55.68, 12.57], 'stockholm': [59.33, 18.07],
  'helsinki': [60.17, 24.94], 'oslo': [59.91, 10.75],
  'warsaw': [52.23, 21.01], 'prague': [50.08, 14.44],
  'budapest': [47.50, 19.04], 'athens': [37.98, 23.73],
  'istanbul': [41.01, 28.98], 'moscow': [55.76, 37.62],
  'dubai': [25.20, 55.27], 'abu dhabi': [24.45, 54.38],
  'riyadh': [24.71, 46.68], 'jeddah': [21.49, 39.19],
  'doha': [25.29, 51.53], 'tel aviv': [32.09, 34.78],
  'cairo': [30.04, 31.24], 'johannesburg': [-26.20, 28.05],
  'cape town': [-33.92, 18.42], 'nairobi': [-1.29, 36.82],
  'lagos': [6.52, 3.38], 'casablanca': [33.57, -7.59],
  'mumbai': [19.08, 72.88], 'new delhi': [28.61, 77.21],
  'delhi': [28.61, 77.21], 'bangalore': [12.97, 77.59],
  'bengaluru': [12.97, 77.59], 'hyderabad': [17.39, 78.49],
  'chennai': [13.08, 80.27], 'pune': [18.52, 73.86],
  'kolkata': [22.57, 88.36], 'ahmedabad': [23.02, 72.57],
  'singapore': [1.35, 103.82], 'kuala lumpur': [3.14, 101.69],
  'bangkok': [13.76, 100.50], 'jakarta': [-6.21, 106.85],
  'manila': [14.60, 120.98], 'ho chi minh city': [10.82, 106.63],
  'hanoi': [21.03, 105.85], 'hong kong': [22.32, 114.17],
  'shanghai': [31.23, 121.47], 'beijing': [39.90, 116.41],
  'shenzhen': [22.54, 114.06], 'guangzhou': [23.13, 113.26],
  'taipei': [25.03, 121.57], 'seoul': [37.57, 126.98],
  'tokyo': [35.68, 139.69], 'osaka': [34.69, 135.50],
  'sydney': [-33.87, 151.21], 'melbourne': [-37.81, 144.96],
  'auckland': [-36.85, 174.76],
}

/* main-hub fallback when the city is unknown */
export const COUNTRY_COORDS = {
  'united states': [39.8, -98.6], 'canada': [45.4, -75.7],
  'mexico': [19.43, -99.13], 'brazil': [-23.55, -46.63],
  'united kingdom': [51.51, -0.13], 'france': [48.86, 2.35],
  'germany': [50.11, 8.68], 'netherlands': [52.37, 4.90],
  'belgium': [50.85, 4.35], 'spain': [40.42, -3.70],
  'portugal': [38.72, -9.14], 'italy': [45.46, 9.19],
  'switzerland': [47.38, 8.54], 'austria': [48.21, 16.37],
  'denmark': [55.68, 12.57], 'sweden': [59.33, 18.07],
  'finland': [60.17, 24.94], 'norway': [59.91, 10.75],
  'poland': [52.23, 21.01], 'czech republic': [50.08, 14.44],
  'hungary': [47.50, 19.04], 'greece': [37.98, 23.73],
  'turkey': [41.01, 28.98], 'russia': [55.76, 37.62],
  'united arab emirates': [25.20, 55.27], 'saudi arabia': [24.71, 46.68],
  'qatar': [25.29, 51.53], 'israel': [32.09, 34.78],
  'egypt': [30.04, 31.24], 'south africa': [-26.20, 28.05],
  'kenya': [-1.29, 36.82], 'nigeria': [6.52, 3.38],
  'morocco': [33.57, -7.59], 'india': [19.08, 72.88],
  'singapore': [1.35, 103.82], 'malaysia': [3.14, 101.69],
  'thailand': [13.76, 100.50], 'indonesia': [-6.21, 106.85],
  'philippines': [14.60, 120.98], 'vietnam': [10.82, 106.63],
  'hong kong': [22.32, 114.17], 'china': [31.23, 121.47],
  'taiwan': [25.03, 121.57], 'south korea': [37.57, 126.98],
  'japan': [35.68, 139.69], 'australia': [-33.87, 151.21],
  'new zealand': [-36.85, 174.76],
}

/* {name, city, country} → {name, city, country, lat, lng} | null */
export function locateEvent(loc) {
  if (!loc) return null
  const city = (loc.city || '').trim().toLowerCase()
  const country = (loc.country || '').trim().toLowerCase()
  const coords = CITY_COORDS[city] || COUNTRY_COORDS[country]
  if (!coords) return null
  return { ...loc, lat: coords[0], lng: coords[1] }
}
