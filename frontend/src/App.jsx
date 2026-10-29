import { feedbackFetch as fetch } from "./requestFeedback.mjs";
import useLiveUpdates from "./useLiveUpdates";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { divIcon } from "leaflet";
import {
  MapContainer,
  Marker,
  Polyline,
  Popup,
  TileLayer,
  useMap,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";
import "./App.css";
import VillaVideoPreview from "./VillaVideoPreview";
import VillaEntrance from "./VillaEntrance";
import MobileCarousel from "./MobileCarousel";
import LandingLoader, { LoadingImage, LoadingVideo } from "./LandingLoader";
import LandingReviews, {ReviewTicker, ReviewStars} from "./LandingReviews";

const API_BASE_URL = (
  (typeof window !== "undefined" &&
    window.__THE_VILLA_API_BASE__) ||
  import.meta.env.VITE_API_URL ||
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

const LANDING_SELECTED_VILLA_KEY =
  "theVillaLandingSelectedVillaId";
const RECENTLY_VIEWED_VILLA_KEY =
  "theVillaRecentlyViewedVillaId";
const VILLA_CATALOG_UPDATED_KEY =
  "theVillaCatalogUpdatedAt";

const HERO_SLIDES = [
  {
    image: "/image1.jpg",
    alt: "The Villa private staycation",
  },
  {
    image: "/image2.jpg",
    alt: "The Villa outdoor area",
  },
  {
    image: "/image3.jpg",
    alt: "The Villa guest area",
  },
  {
    image: "/image4.jpg",
    alt: "The Villa accommodation",
  },
];

function VillaImageCarousel({
  images = [],
  title,
  variant = "card",
  children,
  onOpen,
  selectedIndex,
  onSelect,
}) {
  const [localIndex, setLocalIndex] = useState(0);
  const activeIndex = selectedIndex ?? localIndex;
  const select = onSelect || setLocalIndex;
  const move = (amount) => {
    if (images.length < 2) return;
    select((activeIndex + amount + images.length) % images.length);
  };

  return (
    <div className={`villa-image-carousel villa-image-carousel-${variant}`}>
      <button
        type="button"
        className={variant === "modal" ? "villa-modal-gallery-image" : "villa-image-button"}
        onClick={onOpen}
        aria-label={`View ${title}`}
      >
        {images[activeIndex] ? (
          <LoadingImage key={images[activeIndex]} src={images[activeIndex]} alt={title} />
        ) : (
          <span className="villa-image-empty">Villa photos coming soon</span>
        )}
        {children}
      </button>
      {images.length > 1 && (
        <>
          <button type="button" className="villa-gallery-arrow previous" aria-label="Previous villa photo" onClick={() => move(-1)}>‹</button>
          <button type="button" className="villa-gallery-arrow next" aria-label="Next villa photo" onClick={() => move(1)}>›</button>
          <span className="villa-gallery-count">{activeIndex + 1} / {images.length}</span>
        </>
      )}
    </div>
  );
}

const VILLA_LATITUDE = 13.9210228;
const VILLA_LONGITUDE = 121.1062011;


const ROUTE_SERVICE_URL =
  import.meta.env.VITE_ROUTE_SERVICE_URL ||
  "https://router.project-osrm.org/route/v1/driving";

const MAP_TILE_URL =
  import.meta.env.VITE_MAP_TILE_URL ||
  "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const MAP_TILE_ATTRIBUTION =
  import.meta.env.VITE_MAP_TILE_ATTRIBUTION ||
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

const VILLA_MAP_ICON = divIcon({
  className: "villa-map-icon-wrap",
  html: '<span class="villa-map-pin resort"><span></span></span>',
  iconSize: [32, 42],
  iconAnchor: [16, 40],
  popupAnchor: [0, -38],
});

const GUEST_MAP_ICON = divIcon({
  className: "villa-map-icon-wrap",
  html: '<span class="villa-map-pin guest"><span></span></span>',
  iconSize: [32, 42],
  iconAnchor: [16, 40],
  popupAnchor: [0, -38],
});

function MapViewport({ guestLocation }) {
  const map = useMap();

  useEffect(()=>{
    map.dragging.enable();
    map.touchZoom.enable();
    const observer=new ResizeObserver(()=>map.invalidateSize({pan:false}));
    observer.observe(map.getContainer());
    return()=>observer.disconnect();
  },[map]);

  useEffect(() => {
    const resort = [VILLA_LATITUDE, VILLA_LONGITUDE];

    if (guestLocation) {
      map.fitBounds(
        [
          resort,
          [guestLocation.latitude, guestLocation.longitude],
        ],
        { padding: [52, 52], maxZoom: 15 }
      );
      return;
    }

    map.setView(resort, 15);
  }, [guestLocation, map]);

  return null;
}

function LocationMap({ guestLocation, routeCoordinates }) {
  const [tilesLoading, setTilesLoading] = useState(true);
  const resort = [VILLA_LATITUDE, VILLA_LONGITUDE];

  return (
    <MapContainer
      className="location-map"
      center={resort}
      zoom={15}
      scrollWheelZoom={false}
      dragging={true}
      touchZoom={true}
      doubleClickZoom={true}
      keyboard={true}
      zoomControl
    >
      {tilesLoading && <LandingLoader overlay label="Loading map" />}
      <TileLayer
        eventHandlers={{ loading: () => setTilesLoading(true), load: () => setTilesLoading(false), tileerror: () => setTilesLoading(false) }}
        attribution={MAP_TILE_ATTRIBUTION}
        url={MAP_TILE_URL}
      />

      {routeCoordinates.length > 1 && (
        <Polyline
          positions={routeCoordinates}
          pathOptions={{ color: "#8b5e3c", weight: 5, opacity: 0.82 }}
        />
      )}

      {guestLocation && (
        <Marker
          position={[guestLocation.latitude, guestLocation.longitude]}
          icon={GUEST_MAP_ICON}
        >
          <Popup>Your current location</Popup>
        </Marker>
      )}

      <Marker position={resort} icon={VILLA_MAP_ICON}>
        <Popup>
          <strong>The Villa</strong>
          <br />
          San Jose, Batangas
        </Popup>
      </Marker>

      <MapViewport guestLocation={guestLocation} />
    </MapContainer>
  );
}

function buildDirectionsUrl(location) {
  const query = new URLSearchParams({
    api: "1",
    destination: `${VILLA_LATITUDE},${VILLA_LONGITUDE}`,
    travelmode: "driving",
  });

  if (
    location?.latitude &&
    location?.longitude
  ) {
    query.set(
      "origin",
      `${location.latitude},${location.longitude}`
    );
  }

  return `https://www.google.com/maps/dir/?${query.toString()}`;
}

function calculateDistanceKm(start, end) {
  if (!start || !end) return null;

  const toRadians = (value) =>
    (Number(value) * Math.PI) / 180;

  const earthRadiusKm = 6371;
  const latDifference = toRadians(
    end.latitude - start.latitude
  );
  const lngDifference = toRadians(
    end.longitude - start.longitude
  );

  const startLatitude = toRadians(
    start.latitude
  );
  const endLatitude = toRadians(
    end.latitude
  );

  const haversine =
    Math.sin(latDifference / 2) ** 2 +
    Math.cos(startLatitude) *
      Math.cos(endLatitude) *
      Math.sin(lngDifference / 2) ** 2;

  return (
    earthRadiusKm *
    2 *
    Math.atan2(
      Math.sqrt(haversine),
      Math.sqrt(1 - haversine)
    )
  );
}

function formatTravelTime(totalMinutes) {
  const minutes = Math.max(
    0,
    Math.round(Number(totalMinutes || 0))
  );

  if (minutes < 60) {
    return `${minutes} min`;
  }

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;

  return remainingMinutes
    ? `${hours} hr ${remainingMinutes} min`
    : `${hours} hr`;
}

const DEFAULT_VILLAS = [
  {
    id: "villa-1",
    image: "/family.jpg",
    images: ["/family.jpg"],
    title: "Family Villa",
    price: "From ₱4,500",
    guests: "Up to 8 guests",
    capacity: 8,
    beds: "4 double-sized beds",
    bathrooms: "2 bathrooms",
    stayHours: "3:00 PM – 11:00 AM",
    details:
      "A spacious private villa for family gatherings, celebrations, and relaxing weekend stays.",
    amenities: [
      "Heated plunge pool",
      "Complete kitchen",
      "Smart projector",
      "300 Mbps Wi-Fi",
      "Garden and BBQ area",
      "Free sauna use",
    ],
  },
  {
    id: "villa-2",
    image: "/couple.jpg",
    images: ["/couple.jpg"],
    title: "Comfort Villa",
    price: "From ₱5,500",
    guests: "Up to 8 guests",
    capacity: 8,
    beds: "4 double-sized beds",
    bathrooms: "2 bathrooms",
    stayHours: "3:00 PM – 11:00 AM",
    details:
      "A comfortable private villa for couples, families, and small groups who value privacy and convenience.",
    amenities: [
      "Heated plunge pool",
      "Air-conditioned rooms",
      "Smart TV",
      "Kitchen appliances",
      "Wi-Fi",
      "Private garden",
    ],
  },
  {
    id: "villa-3",
    image: "/barkada.jpg",
    images: ["/barkada.jpg"],
    title: "Group Villa",
    price: "From ₱6,500",
    guests: "Up to 8 guests",
    capacity: 8,
    beds: "4 double-sized beds",
    bathrooms: "2 bathrooms",
    stayHours: "3:00 PM – 11:00 AM",
    details:
      "A roomy villa with shared spaces for barkada bonding, birthdays, and overnight celebrations.",
    amenities: [
      "Group lounge",
      "Smart projector",
      "Kitchen access",
      "BBQ area",
      "Wi-Fi",
      "Parking",
    ],
  },
  {
    id: "villa-4",
    image: "/image4.jpg",
    images: ["/image4.jpg"],
    title: "Intimate Villa",
    price: "From ₱7,500",
    guests: "Up to 4 guests",
    capacity: 4,
    beds: "2 double-sized beds",
    bathrooms: "1 bathroom",
    stayHours: "3:00 PM – 11:00 AM",
    details:
      "A quieter private villa for couples, small families, and guests looking for a relaxed stay.",
    amenities: [
      "Private plunge pool",
      "Two double beds",
      "Smart TV",
      "Kitchen",
      "Wi-Fi",
      "Garden area",
    ],
  },
];

const FAQS = [
  {
    question: "Do I need an account to book?",
    answer:
      "No. You can make a reservation by completing the booking form with your contact and stay details.",
  },
  {
    question: "How do I check available dates?",
    answer:
      "Select Book now on your preferred villa. The booking page will show the current date availability before you continue.",
  },
  {
    question: "What payment methods are available?",
    answer:
      "Available online payment options may include GCash, Maya, cards, and QR Ph.",
  },
  {
    question: "Can I pay a downpayment?",
    answer:
      "A 50% downpayment or full payment is required to confirm your reservation. Your selected dates are reserved only after payment is verified.",
  },
  {
    question: "Are payments refundable?",
    answer: "Payments are non-refundable. Please confirm your travel dates, villa selection, and guest details before paying.",
  },
  {
    question: "Can I add a special request?",
    answer:
      "Yes. Add your request in the notes field when you make your reservation.",
  },
];

const POLICIES = [
  {
    title: "Downpayment required",
    text: "Pay the required 50% downpayment or the full amount to confirm your reservation. Dates are secured after payment is verified.",
  },
  {
    title: "No refunds",
    text: "Payments are non-refundable. Please review your dates, selected villa, and booking details before completing payment.",
  },
  {
    title: "Booking confirmation",
    text: "Use a valid email address when booking. Your reservation details and confirmation will be sent there once payment is verified.",
  },
  {
    title: "Guest capacity",
    text: "Check your chosen villa’s capacity and enter the correct guest count before proceeding with your reservation.",
  },
];


function Icon({ name, size = 20 }) {
  const icons = {
    arrow: <path d="M5 12h14M13 5l7 7-7 7" />,
    bath: (
      <>
        <path d="M4 12h16v3a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5v-3Z" />
        <path d="M7 12V6a3 3 0 0 1 6 0M8 20v2M16 20v2" />
      </>
    ),
    bed: (
      <>
        <path d="M3 11v9M21 11v9M3 17h18" />
        <path d="M5 17v-6h14a2 2 0 0 1 2 2v4M5 11V7h5a3 3 0 0 1 3 3v1" />
      </>
    ),
    calendar: (
      <>
        <rect x="3" y="5" width="18" height="16" rx="2" />
        <path d="M8 3v4M16 3v4M3 10h18" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
    clock: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </>
    ),
    close: <path d="M6 6l12 12M18 6 6 18" />,
    star: <path d="m12 3 2.7 5.47 6.03.88-4.36 4.25 1.03 6.01L12 16.77l-5.4 2.84 1.03-6.01-4.36-4.25 6.03-.88L12 3Z" />,
    pin: (
      <>
        <path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z" />
        <circle cx="12" cy="10" r="2.5" />
      </>
    ),
    route: (
      <>
        <circle cx="6" cy="18" r="2" />
        <circle cx="18" cy="6" r="2" />
        <path d="M8 18h3a4 4 0 0 0 4-4v-4a4 4 0 0 1 4-4h1" />
      </>
    ),
    users: (
      <>
        <circle cx="9" cy="8" r="3" />
        <circle cx="17" cy="8" r="3" />
        <path d="M3 21c1-4 3-6 6-6s5 2 6 6M14 15c3 0 5 2 6 6" />
      </>
    ),
  };

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {icons[name]}
    </svg>
  );
}

function formatCatalogPrice(value) {
  return `From ₱${Number(value || 0).toLocaleString("en-PH", {
    maximumFractionDigits: 0,
  })}`;
}

function flattenAmenities(value) {
  if (!Array.isArray(value)) return [];

  return value
    .flatMap((group) => {
      if (typeof group === "string") return [group];
      if (Array.isArray(group?.items)) return group.items;
      return [];
    })
    .map((item) => String(item || "").trim())
    .filter(Boolean)
    .slice(0, 12);
}

function normalizeCatalog(rows) {
  const sourceRows = Array.isArray(rows) ? rows : [];
  const sourceById = new Map(
    sourceRows
      .filter((row) => row?.id)
      .map((row) => [String(row.id), row])
  );

  const fallbackById = new Map(
    DEFAULT_VILLAS.map((villa) => [villa.id, villa])
  );

  const normalizeOne = (row, fallback) => {
    const amenities = flattenAmenities(row?.amenities);
    const capacity = Number(row?.capacity || fallback.capacity || 1);

    return {
      ...fallback,
      id: row?.id || fallback.id,
      images: Array.isArray(row?.image_urls)
        ? row.image_urls.map((url) => String(url || "").trim()).filter(Boolean)
        : [row?.image_url || row?.image || fallback.image].filter(Boolean),
      image: Array.isArray(row?.image_urls)
        ? row.image_urls[0] || ""
        : row?.image_url || row?.image || fallback.image,
      title: row?.landing_title || row?.title || row?.name || fallback.title,
      price:
        row?.price !== undefined && row?.price !== null
          ? formatCatalogPrice(row.price)
          : fallback.price,
      guests: row?.guest_label || `Up to ${capacity} guests`,
      capacity,
      beds: row?.beds || fallback.beds,
      bathrooms: row?.bathrooms || fallback.bathrooms,
      stayHours:
        row?.stay_hours ||
        row?.stayHours ||
        fallback.stayHours,
      details:
        row?.details ||
        row?.short_description ||
        row?.description ||
        fallback.details,
      amenities: amenities.length ? amenities : fallback.amenities,
    };
  };

  const standardVillas = DEFAULT_VILLAS.map((fallback) =>
    normalizeOne(sourceById.get(fallback.id), fallback)
  );

  const extraVillas = sourceRows
    .filter(
      (row) =>
        row?.id &&
        !fallbackById.has(String(row.id))
    )
    .map((row) => normalizeOne(row, DEFAULT_VILLAS[0]));

  return [...standardVillas, ...extraVillas];
}


function App() {
  const navigate = useNavigate();
  const [catalogRevision, setCatalogRevision] = useState(0);
  const [reviewRevision, setReviewRevision] = useState(0);
  useLiveUpdates({ audience: "public", domains: ["catalog"], onChange: () => setCatalogRevision(value => value + 1) });
  useLiveUpdates({ audience: "public", domains: ["reviews"], onChange: () => setReviewRevision(value => value + 1) });

  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [villas, setVillas] = useState(DEFAULT_VILLAS);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [selectedVilla, setSelectedVilla] = useState(null);
  const [selectedVillaImageIndex, setSelectedVillaImageIndex] = useState(0);
  const [videoOpen, setVideoOpen] = useState(false);
  const [openFaq, setOpenFaq] = useState(0);
  const [heroIndex, setHeroIndex] = useState(0);
  const [reviewStep, setReviewStep] = useState(0);
  const [feedbackSummary, setFeedbackSummary] = useState(null);
  const [feedbackSummaryState, setFeedbackSummaryState] = useState("loading");

  const [guestLocation, setGuestLocation] =
    useState(null);

  const [locationStatus, setLocationStatus] =
    useState({
      type: "idle",
      message:
        "Get directions to see distance and estimated travel time.",
    });

  const [routeInfo, setRouteInfo] =
    useState({
      distanceKm: null,
      durationMinutes: null,
      directDistanceKm: null,
    });

  const [routeCoordinates, setRouteCoordinates] = useState([]);

  const directionsUrl =
    buildDirectionsUrl(guestLocation);

  const scrollTo = (id) => {
    setMenuOpen(false);

    const destination = document.getElementById(id);
    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      destination?.querySelectorAll("h2, .section-label, .section-heading > span").forEach((element, index) => {
        element.getAnimations().forEach(animation => animation.cancel());
        element.animate([
          { opacity: 0.3, transform: "translateY(16px)" },
          { opacity: 1, transform: "translateY(0)" },
        ], { duration: 850, delay: 120 + index * 70, easing: "cubic-bezier(.16,1,.3,1)" });
      });
    }
    destination?.scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth",
      block: "start",
    });
  };

  useEffect(() => {
    const root = document.querySelector(".app");
    if (!root || !("IntersectionObserver" in window)) return undefined;
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sections = [...root.querySelectorAll("main > section[id]")];
    const targets = [...root.querySelectorAll(".section > .container > *, .villa-grid > *, .policy-grid > *, .about-visual, .about-copy > *, .faq-item")];
    targets.forEach((element, index) => {
      element.classList.add("section-reveal");
      element.style.setProperty("--reveal-delay", `${(index % 3) * 85}ms`);
    });
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(({ target, isIntersecting }) => {
        if (isIntersecting) target.classList.add("is-visible");
        else target.classList.remove("is-visible");
      });
    }, { threshold: 0.08 });
    targets.forEach(element => observer.observe(element));
    const updateNavigation = () => {
      const line = window.innerHeight * 0.35;
      const current = sections.filter(section => section.getBoundingClientRect().top <= line).at(-1);
      root.querySelectorAll(".desktop-nav button, .mobile-menu button, .footer-links button").forEach(button => {
        const label = button.textContent.trim().toLowerCase();
        const id = label === "feedback" ? "guest-feedback" : label;
        if (id === current?.id) button.setAttribute("aria-current", "location");
        else button.removeAttribute("aria-current");
      });
    };
    const syncMotion = () => root.classList.toggle("has-section-motion", !motion.matches);
    syncMotion();
    updateNavigation();
    window.addEventListener("scroll", updateNavigation, { passive: true });
    motion.addEventListener("change", syncMotion);
    return () => {
      observer.disconnect();
      root.classList.remove("has-section-motion");
      motion.removeEventListener("change", syncMotion);
      window.removeEventListener("scroll", updateNavigation);
    };
  }, []);

  const openVilla = (villa) => {
    try {
      window.sessionStorage.setItem(
        RECENTLY_VIEWED_VILLA_KEY,
        villa.id
      );
    } catch {
      // Viewing still works if storage is unavailable.
    }

    setSelectedVilla(villa);
    setSelectedVillaImageIndex(0);
  };

  const closeVilla = () => {
    setSelectedVilla(null);
  };

  const openBooking = (
    villaId = "",
    villaCapacity = ""
  ) => {
    setMenuOpen(false);
    closeVilla();

    const query = new URLSearchParams();

    if (typeof villaId === "string" && villaId) {
      query.set("villa", villaId);
      query.set("source", "landing-villa");

      const numericCapacity = Number(
        villaCapacity
      );

      if (
        Number.isFinite(numericCapacity) &&
        numericCapacity > 0
      ) {
        query.set(
          "guests",
          String(numericCapacity)
        );
      }

      try {
        window.sessionStorage.setItem(
          LANDING_SELECTED_VILLA_KEY,
          villaId
        );

        window.sessionStorage.setItem(
          RECENTLY_VIEWED_VILLA_KEY,
          villaId
        );
      } catch {
        // The URL still carries the villa if storage is unavailable.
      }
    } else {
      try {
        window.sessionStorage.removeItem(
          LANDING_SELECTED_VILLA_KEY
        );
      } catch {
        // Ignore storage cleanup errors.
      }
    }

    const value = query.toString();
    navigate(value ? `/book?${value}` : "/book");
  };

  const getDirectionsInSite = () => {
    if (!navigator.geolocation) {
      setLocationStatus({
        type: "error",
        message:
          "Location services are not supported by this browser.",
      });
      return;
    }

    setLocationStatus({
      type: "loading",
      message:
        "Finding the best route to The Villa…",
    });

    setRouteInfo({
      distanceKm: null,
      durationMinutes: null,
      directDistanceKm: null,
    });
    setRouteCoordinates([]);

    navigator.geolocation.getCurrentPosition(
      async (position) => {
        const location = {
          latitude:
            position.coords.latitude,
          longitude:
            position.coords.longitude,
          accuracy:
            position.coords.accuracy,
        };

        setGuestLocation(location);

        const directDistanceKm =
          calculateDistanceKm(
            location,
            {
              latitude:
                VILLA_LATITUDE,
              longitude:
                VILLA_LONGITUDE,
            }
          );

        try {
          const coordinates =
            `${location.longitude},${location.latitude};` +
            `${VILLA_LONGITUDE},${VILLA_LATITUDE}`;

          const query =
            new URLSearchParams({
              overview: "full",
              steps: "false",
              alternatives: "false",
              geometries: "geojson",
            });

          const response = await fetch(
            `${ROUTE_SERVICE_URL}/${coordinates}?${query.toString()}`,
            {
              headers: {
                Accept:
                  "application/json",
              },
            }
          );

          if (!response.ok) {
            throw new Error(
              "Route details are unavailable."
            );
          }

          const payload =
            await response.json();

          const route =
            payload?.routes?.[0];

          if (!route) {
            throw new Error(
              "No driving route was found."
            );
          }

          setRouteInfo({
            distanceKm:
              Number(
                route.distance || 0
              ) / 1000,
            durationMinutes:
              Number(
                route.duration || 0
              ) / 60,
            directDistanceKm,
          });
          setRouteCoordinates(
            Array.isArray(route.geometry?.coordinates)
              ? route.geometry.coordinates.map(
                  ([longitude, latitude]) => [latitude, longitude]
                )
              : []
          );

          setLocationStatus({
            type: "success",
            message:
              "Directions are displayed on the map.",
          });
        } catch {
          setRouteInfo({
            distanceKm: null,
            durationMinutes: null,
            directDistanceKm,
          });

          setLocationStatus({
            type: "success",
            message:
              "Directions are displayed on the map. Open Google Maps for detailed travel information.",
          });
        }
      },
      (error) => {
        const messages = {
          1:
            "Location permission was not granted. Please allow location access to view directions.",
          2:
            "Unable to detect your location. Please turn on location services and try again.",
          3:
            "Your browser could not determine your location in time. Check that this site uses HTTPS, allow location access in your browser, and enable Location Services on your device. You can still open Google Maps for directions.",
        };

        console.warn("Geolocation error:", error);

        setGuestLocation(null);
        setRouteInfo({
          distanceKm: null,
          durationMinutes: null,
          directDistanceKm: null,
        });
        setRouteCoordinates([]);

        setLocationStatus({
          type: "error",
          message:
            messages[error.code] ||
            "Your location could not be loaded.",
        });
      },
      {
        // Allow Wi-Fi/network location fallback instead of requiring GPS only
        enableHighAccuracy: false,
        timeout: 60000,
        maximumAge: 600000,
      }
    );
  };

  const showNextHero = () => {
    setReviewStep(current=>current+1);
    setHeroIndex((current) =>
      (current + 1) %
      HERO_SLIDES.length
    );
  };

  useEffect(() => {
    const timer = window.setInterval(
      showNextHero,
      5000
    );

    return () =>
      window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let active = true;

    const loadCatalog = async () => {
      try {
        const response = await fetch(
          `${API_BASE_URL}/villa-catalog/public`,
          {
            headers: { Accept: "application/json" },
          }
        );

        if (!response.ok) {
          throw new Error("Catalog unavailable.");
        }

        const payload = await response.json();

        if (active) {
          setVillas(normalizeCatalog(payload?.data));
        }
      } catch {
        if (active) {
          setVillas(DEFAULT_VILLAS);
        }
      } finally {
        if (active) setCatalogLoading(false);
      }
    };

    loadCatalog();

    window.addEventListener("focus", loadCatalog);
    const handleCatalogUpdate = (event) => {
      if (event.key === VILLA_CATALOG_UPDATED_KEY) loadCatalog();
    };
    window.addEventListener("storage", handleCatalogUpdate);

    return () => {
      active = false;
      window.removeEventListener("focus", loadCatalog);
      window.removeEventListener("storage", handleCatalogUpdate);
    };
  }, [catalogRevision]);

  useEffect(() => {
    let active = true;

    const loadFeedbackSummary = async () => {
      try {
        const response = await fetch(
          `${API_BASE_URL}/public-bookings/feedback/reviews`,
          {
            headers: { Accept: "application/json" },
            cache: "no-store",
          }
        );

        if (!response.ok) {
          throw new Error("Guest ratings are temporarily unavailable.");
        }

        const payload = await response.json();
        const summary = payload?.data;
        if (
          !summary ||
          !Number.isInteger(summary.count) ||
          summary.count < 0 ||
          (summary.count > 0 &&
            (!Number.isFinite(summary.average) ||
              summary.average < 1 ||
              summary.average > 5))
        ) {
          throw new Error("The guest rating summary is invalid.");
        }

        if (active) {
          setFeedbackSummary({
            reviews: Array.isArray(summary.reviews)?summary.reviews:[],
            count: summary.count,
            average: summary.count ? summary.average : null,
            distribution: Object.fromEntries(
              [1, 2, 3, 4, 5].map((rating) => [
                rating,
                Math.max(0, Number(summary.distribution?.[String(rating)]) || 0),
              ])
            ),
          });
          setFeedbackSummaryState("ready");
        }
      } catch {
        if (active) setFeedbackSummaryState("unavailable");
      }
    };

    loadFeedbackSummary();
    window.addEventListener("focus", loadFeedbackSummary);

    return () => {
      active = false;
      window.removeEventListener("focus", loadFeedbackSummary);
    };
  }, [reviewRevision]);

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 16);

    handleScroll();
    window.addEventListener("scroll", handleScroll, { passive: true });

    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    if (!menuOpen && !selectedVilla && !videoOpen) return undefined;

    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
        closeVilla();
        setVideoOpen(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [menuOpen, selectedVilla, videoOpen]);

  return (
    <div className="app">
      <header className={`site-header ${scrolled ? "scrolled" : ""}`}>
        <div className="header-inner">
          <button
            type="button"
            className="brand"
            onClick={() => scrollTo("home")}
          >
            <img src="/favicon.png" alt="The Villa" />
            <span>
              <strong>The Villa</strong>
              <small>Batangas Private Staycation</small>
            </span>
          </button>

          <nav className="desktop-nav" aria-label="Main navigation">
            <button type="button" onClick={() => scrollTo("home")}>Home</button>
            <button type="button" onClick={() => scrollTo("villas")}>Villas</button>
            <button type="button" onClick={() => scrollTo("about")}>About</button>
            <button type="button" onClick={() => scrollTo("location")}>Location</button>
            <button type="button" onClick={() => scrollTo("faqs")}>FAQs</button>
            <button type="button" onClick={() => scrollTo("guest-feedback")}>Feedback</button>
          </nav>

          <div className="header-actions">
            <button
              type="button"
              className="primary-action compact"
              onClick={() => openBooking()}
            >
              Book now
            </button>

            <button
              type="button"
              className={`menu-button ${menuOpen ? "active" : ""}`}
              aria-label={menuOpen ? "Close menu" : "Open menu"}
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((current) => !current)}
            >
              <span />
              <span />
              <span />
            </button>
          </div>
        </div>
      </header>

      <button
        type="button"
        className={`menu-backdrop ${menuOpen ? "show" : ""}`}
        aria-label="Close menu"
        onClick={() => setMenuOpen(false)}
      />

      <aside className={`mobile-menu ${menuOpen ? "open" : ""}`}>
        <div className="mobile-menu-brand">
          <img src="/favicon.png" alt="" />
          <div>
            <strong>The Villa</strong>
            <span>Private Staycation</span>
          </div>
        </div>

        <nav>
          <button type="button" onClick={() => scrollTo("home")}>Home</button>
          <button type="button" onClick={() => scrollTo("villas")}>Villas</button>
          <button type="button" onClick={() => scrollTo("about")}>About</button>
          <button type="button" onClick={() => scrollTo("location")}>Location</button>
          <button type="button" onClick={() => scrollTo("faqs")}>FAQs</button>
            <button type="button" onClick={() => scrollTo("guest-feedback")}>Feedback</button>
        </nav>

        <button
          type="button"
          className="primary-action"
          onClick={() => openBooking()}
        >
          Book your stay
        </button>
      </aside>

      <main>
        <section className="hero-section" id="home">
          <div className="hero-carousel" aria-label="The Villa gallery">
            {HERO_SLIDES.map((slide, index) => (
              <LoadingImage
                active={index === heroIndex}
                key={slide.image}
                className={`hero-slide ${
                  index === heroIndex ? "active" : ""
                }`}
                src={slide.image}
                alt={slide.alt}
              />
            ))}
          </div>

          <div className="hero-overlay" />
          <VillaEntrance photoSrc={HERO_SLIDES[0].image} />

          <div className="container hero-inner">
            <div className="hero-content">
              <div className="hero-message">
              <h1>Unwind and make moments to remember in your own private villa.</h1>
              <p>Enjoy a thoughtfully appointed retreat with room to relax, recharge, and enjoy your stay at your own pace.</p>
              </div>
              <div className="hero-controls">

              <div className="hero-actions">
                <button
                  type="button"
                  className="primary-action"
                  onClick={() => openBooking()}
                >
                  Book your stay
                  <Icon name="arrow" size={18} />
                </button>

                <button
                  type="button"
                  className="primary-action"
                  onClick={() => scrollTo("villas")}
                >
                  View villas
                </button>
              </div>


              </div>
            </div>
            <aside className="hero-social-proof" aria-label="Guest ratings and experiences">
              <button
                type="button"
                className="hero-rating-summary"
                onClick={() => scrollTo("guest-feedback")}
                aria-label="View ratings"
              >
                <span className="hero-rating-stars" aria-hidden="true">
                  {[1, 2, 3, 4, 5].map((rating) => (
                    <span
                      key={rating}
                      className={
                        feedbackSummary?.count &&
                        rating <= Math.round(feedbackSummary.average)
                          ? "is-filled"
                          : ""
                      }
                    >
                      <Icon name="star" size={14} />
                    </span>
                  ))}
                </span>
                <span className="hero-rating-copy">
                  {feedbackSummaryState === "loading" ? (
                    <LandingLoader compact label="Loading ratings" />
                  ) : feedbackSummaryState === "unavailable" ? (
                    <span>Ratings temporarily unavailable</span>
                  ) : feedbackSummary?.count ? (
                    <>
                      <strong>{feedbackSummary.average.toFixed(1)} / 5</strong>
                      <span>
                        from {feedbackSummary.count}{" "}
                        {feedbackSummary.count === 1 ? "review" : "reviews"}
                      </span>
                    </>
                  ) : (
                    <span>Be among the first to share a rating</span>
                  )}
                </span>

              </button>
              <ReviewTicker reviews={feedbackSummary?.reviews || []} step={reviewStep}/>
            </aside>
          </div>

        </section>

        <section className="section villas-section" id="villas">
          <div className="container content-container">
            <div className="section-heading">
              <span>Our villas</span>
              <h2>Find the space that fits your stay.</h2>
              <p>
                Explore each private stay, compare its character and amenities,
                then book the villa that feels right for your getaway.
              </p>
            </div>

            {catalogLoading && <div className="landing-loading-row"><LandingLoader label="Loading villas" /></div>}
            <MobileCarousel className="villa-grid" label="villas" count={villas.length}>
              {villas.map((villa, index) => {
                const villaLabels = [
                  "Family escape",
                  "Comfort retreat",
                  "Group favorite",
                  "Quiet hideaway",
                ];

                return (
                  <article
                    className={`villa-card villa-card-${(index % 4) + 1}`}
                    key={villa.id}
                  >
                    <VillaImageCarousel
                      key={`${villa.id}-${villa.images.join("|")}`}
                      images={villa.images}
                      title={villa.title}
                      onOpen={() => openVilla(villa)}
                    >
                      <span className="villa-card-shade" />
                      <span className="villa-card-kicker">
                        {villaLabels[index % villaLabels.length]}
                      </span>
                      <span className="villa-card-image-meta">
                        <b>{villa.guests}</b>
                        <small>{villa.stayHours}</small>
                      </span>
                    </VillaImageCarousel>

                    <div className="villa-card-body">
                      <div className="villa-card-topline">
                        <span>Private villa</span>
                        <strong>{villa.price}</strong>
                      </div>

                      <div className="villa-card-title">
                        <div>
                          <h3>{villa.title}</h3>
                          <p>{villa.details}</p>
                        </div>
                      </div>

                      <div className="villa-card-highlights">
                        <span>
                          <Icon name="bed" size={15} />
                          {villa.beds}
                        </span>
                        <span>
                          <Icon name="bath" size={15} />
                          {villa.bathrooms}
                        </span>
                      </div>

                      <div className="villa-card-feature">
                        <span>Featured amenity</span>
                        <strong>{villa.amenities?.[0] || "Private stay"}</strong>
                      </div>

                      <div className="villa-card-actions">
                        <button
                          type="button"
                          className="secondary-action"
                          onClick={() => openVilla(villa)}
                        >
                          View details
                          <Icon name="arrow" size={14} />
                        </button>

                        <button
                          type="button"
                          className="primary-action"
                          onClick={() =>
                            openBooking(
                              villa.id,
                              villa.capacity
                            )
                          }
                        >
                          Book now
                          <Icon name="arrow" size={16} />
                        </button>
                      </div>
                    </div>
                  </article>
                );
              })}
            </MobileCarousel>
          </div>
        </section>

        <section className="section about-section" id="about">
          <div className="container content-container">
            <div className="about-shell">
              <div className="about-visual">
                <VillaVideoPreview onOpen={()=>setVideoOpen(true)}/>
                <div className="about-film-caption"><span>San Jose, Batangas</span><span>Space to slow down.</span></div>
              </div>

              <div className="about-copy">
                <div className="about-intro">
                  <img
                    className="about-brand-mark"
                    src="/favicon.png"
                    alt="The Villa"
                  />
                  <span className="section-label">About The Villa</span>

                  <h2>
                    A private retreat in the heart of Batangas.
                  </h2>

                  <p className="about-lead">
                    The Villa provides thoughtfully appointed private
                    accommodations in San Jose, Batangas. Designed for families
                    and groups, the property brings together comfortable living
                    spaces, private amenities, and room to gather for a
                    well-considered stay.
                  </p>
                </div>

                <div className="about-divider" />

                <div className="about-values">
                  <article>
                    <span>01</span>
                    <div>
                      <h3>Private accommodations</h3>
                      <p>
                        Comfortable, private spaces designed to give each guest
                        room to relax throughout their stay.
                      </p>
                    </div>
                  </article>

                  <article>
                    <span>02</span>
                    <div>
                      <h3>Well-appointed facilities</h3>
                      <p>
                        Pool facilities, practical kitchen amenities, and
                        shared areas support stays for a range of occasions.
                      </p>
                    </div>
                  </article>

                  <article>
                    <span>03</span>
                    <div>
                      <h3>Designed for gatherings</h3>
                      <p>
                        Flexible common spaces provide a welcoming setting for
                        family visits, celebrations, and group getaways.
                      </p>
                    </div>
                  </article>
                </div>

                <div className="about-note">
                  <span className="about-note-mark">“</span>
                  <p>
                    A considered private stay for families and groups in
                    San Jose, Batangas.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="section location-section" id="location">
          <div className="container content-container location-container">
            <div className="location-card">
              <div className="map-frame">
                <LocationMap guestLocation={guestLocation} routeCoordinates={routeCoordinates}/>
                <div className="map-heading-overlay"><span>Find us</span><h2>Your next escape, in San Jose.</h2><p>The Villa · San Jose, Batangas</p></div>
                {guestLocation && <div className="map-trip-metrics" aria-live="polite"><div><small>{routeInfo.distanceKm!==null?'Driving distance':'Straight-line distance'}</small><strong>{locationStatus.type==='loading'?<LandingLoader compact label="Calculating distance" />:routeInfo.distanceKm!==null?`${routeInfo.distanceKm.toFixed(1)} km`:routeInfo.directDistanceKm!==null?`${routeInfo.directDistanceKm.toFixed(1)} km`:'Calculating…'}</strong></div><div><small>Estimated travel</small><strong>{routeInfo.durationMinutes!==null?formatTravelTime(routeInfo.durationMinutes):'Unavailable'}</strong></div></div>}
                <div className="map-destination-card">
                  <div className="map-destination-copy"><span className="map-destination-icon"><Icon name="pin" size={20}/></span><div><h3>The Villa</h3><span>San Jose, Batangas</span><p className={`map-status ${locationStatus.type}`} role="status">{locationStatus.type === "loading" ? null : locationStatus.message}</p></div></div>
                  <div className="map-destination-actions"><button type="button" className="primary-action" onClick={getDirectionsInSite} disabled={locationStatus.type==='loading'}>{locationStatus.type==='loading'?<LandingLoader compact label="Finding directions" />:<><Icon name="route" size={16}/>{guestLocation?'Update directions':'Get directions'}</>}</button><a className="secondary-action" href={directionsUrl} target="_blank" rel="noreferrer">Google Maps<Icon name="arrow" size={16}/></a></div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="section faq-section" id="faqs">
          <div className="container content-container faq-layout">
            <div className="faq-intro">
              <span className="section-label">FAQs</span>
              <h2>Before you book.</h2>
              <p>
                Answers to common questions about reservations, dates, and
                payments.
              </p>
            </div>

            <div className="faq-list">
              {FAQS.map((faq, index) => {
                const open = openFaq === index;

                return (
                  <article
                    className={`faq-item ${open ? "open" : ""}`}
                    key={faq.question}
                  >
                    <button
                      type="button"
                      aria-expanded={open}
                      onClick={() => setOpenFaq(open ? -1 : index)}
                    >
                      <span>{faq.question}</span>
                      <b>{open ? "−" : "+"}</b>
                    </button>

                    <div className="faq-answer">
                      <p>{faq.answer}</p>
                    </div>
                  </article>
                );
              })}
            </div>
          </div>
        </section>

        <section className="section landing-feedback-section" id="guest-feedback">
          <div className="container content-container">
            <div className="landing-feedback-heading"><div><span className="section-label">Reviews</span><h2>A few words from our guests.</h2></div>
              {feedbackSummary?.count>0 && <div className="landing-feedback-total" aria-label={`Average guest rating ${feedbackSummary.average} out of 5 from ${feedbackSummary.count} reviews`}><div className="landing-rating-number"><small>Overall rating</small><strong>{feedbackSummary.average.toFixed(1)}<span>/ 5</span></strong></div><div className="landing-rating-detail"><ReviewStars rating={feedbackSummary.average}/><small>Based on {feedbackSummary.count} reviews</small></div></div>}
              <img className="section-villa-logo" src="/favicon.png" alt="The Villa" loading="lazy" width="64" height="64"/>
            </div>
            <LandingReviews reviews={feedbackSummary?.reviews || []}/>
            {feedbackSummaryState==='loading' && <div className="landing-loading-row"><LandingLoader label="Loading reviews" /></div>}
            {feedbackSummaryState==='unavailable' && <p className="landing-feedback-status" role="status">Reviews are temporarily unavailable.</p>}
            {feedbackSummaryState==='ready' && !feedbackSummary?.count && <p className="landing-feedback-status">Our guests’ experiences will appear here.</p>}
          </div>
        </section>

        <section className="section policies-section" id="policies">
          <div className="container content-container">
            <div className="section-heading light">
              <span>Booking guidelines</span>
              <h2>What to know before you book.</h2>
            </div>

            <div className="policy-grid">
              {POLICIES.map((policy) => (
                <article key={policy.title}>
                  <h3>{policy.title}</h3>
                  <p>{policy.text}</p>
                </article>
              ))}
            </div>

            <div className="center-action">
              <button type="button" className="policy-help-link" onClick={()=>scrollTo("faqs")}>
                Have a question? Explore our FAQs <Icon name="arrow" size={16}/>
              </button>
            </div>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <div className="container content-container footer-main">
          <div className="footer-brand">
            <img src="/favicon.png" alt="The Villa" />
            <div>
              <strong>The Villa</strong>
              <span>Batangas Private Staycation</span>
            </div>
          </div>

          <nav className="footer-links">
            <button type="button" onClick={() => scrollTo("villas")}>Villas</button>
            <button type="button" onClick={() => scrollTo("location")}>Location</button>
            <button type="button" onClick={() => scrollTo("faqs")}>FAQs</button>
            <button type="button" onClick={() => scrollTo("guest-feedback")}>Feedback</button>
          </nav>

          <button
            type="button"
            className="primary-action compact"
            onClick={() => openBooking()}
          >
            Book now
          </button>
        </div>

        <div className="container content-container footer-bottom">
          © {new Date().getFullYear()} The Villa. All rights reserved.
        </div>
      </footer>

      {selectedVilla && (
        <div
          className="modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-label={`${selectedVilla.title} details`}
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              closeVilla();
            }
          }}
        >
          <div className="villa-modal">
            <button
              type="button"
              className="modal-close"
              onClick={closeVilla}
              aria-label="Close villa details"
            >
              <Icon name="close" size={19} />
            </button>

            <VillaImageCarousel
              key={`${selectedVilla.id}-${selectedVilla.images.join("|")}`}
              images={selectedVilla.images}
              title={selectedVilla.title}
              variant="modal"
              selectedIndex={selectedVillaImageIndex}
              onSelect={setSelectedVillaImageIndex}
            >
              <span className="modal-photo-tag">Private stay · San Jose, Batangas</span>
            </VillaImageCarousel>

            <div className="villa-modal-info">
              <div className="modal-body">
                <span className="section-label">Accommodation details</span>

                <div className="modal-title">
                  <h2>{selectedVilla.title}</h2>
                  <strong>{selectedVilla.price}</strong>
                </div>

                <p className="modal-description">{selectedVilla.details}</p>

                <h3 className="modal-subheading">At a glance</h3>
                <div className="villa-specs">
                  <article>
                    <Icon name="users" size={18} />
                    <span>{selectedVilla.guests}</span>
                  </article>
                  <article>
                    <Icon name="bed" size={18} />
                    <span>{selectedVilla.beds}</span>
                  </article>
                  <article>
                    <Icon name="bath" size={18} />
                    <span>{selectedVilla.bathrooms}</span>
                  </article>
                  <article>
                    <Icon name="clock" size={18} />
                    <span>{selectedVilla.stayHours}</span>
                  </article>
                </div>

                <h3 className="modal-subheading">Amenities and facilities</h3>

                <div className="amenities">
                  {selectedVilla.amenities.map((amenity) => (
                    <span key={amenity}>
                      <Icon name="check" size={14} />
                      {amenity}
                    </span>
                  ))}
                </div>
              </div>

              <div className="modal-actions">
                <button
                  type="button"
                  className="primary-action"
                  onClick={() =>
                    openBooking(
                      selectedVilla.id,
                      selectedVilla.capacity
                    )
                  }
                >
                  Book now
                  <Icon name="arrow" size={16} />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {videoOpen && (
        <div
          className="video-modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-label="The Villa video"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              setVideoOpen(false);
            }
          }}
        >
          <div className="video-modal">
            <button
              type="button"
              className="video-modal-close"
              onClick={() => setVideoOpen(false)}
              aria-label="Close video"
            >
              <Icon name="close" size={20} />
            </button>

            <LoadingVideo
              src="/ads.mp4"
              controls
              autoPlay
              playsInline
              className="video-modal-player"
            />
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
