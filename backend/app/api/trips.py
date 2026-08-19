import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Response, status
from sqlalchemy.orm import Session

from app.api.me import get_recommendation_provider
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.models.personalization import Flight
from app.models.product import Product
from app.models.trip import HotelStay, Trip, VisitReservation
from app.providers.recommendation import RecommendationProvider
from app.schemas.api import (
    ErrorResponse,
    FeedRecommendationResponse,
    FeedStoreResponse,
    FeedTripResponse,
    FlightResponse,
    HotelStayRequest,
    HotelStayResponse,
    ProductResponse,
    ReservationStoreResponse,
    StoreWishlistProductResponse,
    TripCreateRequest,
    TripDetailResponse,
    TripFeedResponse,
    TripListResponse,
    TripPatchRequest,
    TripResponse,
    VisitReservationCreateRequest,
    VisitReservationResponse,
)
from app.services.recommendations import RecommendationResult, RecommendationService
from app.services.trips import TripService

router = APIRouter(prefix="/api/v1/me", tags=["trip-shopping"])
logger = logging.getLogger(__name__)
DbSession = Annotated[Session, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]
RecommendationProviderDependency = Annotated[
    RecommendationProvider,
    Depends(get_recommendation_provider),
]


@router.post(
    "/trips",
    response_model=TripResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_trip(payload: TripCreateRequest, db: DbSession) -> TripResponse:
    trip = TripService(db).create_trip(payload.model_dump())
    return _trip_response(trip)


@router.get("/trips", response_model=TripListResponse)
def list_trips(db: DbSession) -> TripListResponse:
    return TripListResponse(trips=[_trip_response(trip) for trip in TripService(db).list_trips()])


@router.get(
    "/trips/{tripId}",
    response_model=TripDetailResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_trip(
    trip_id: Annotated[UUID, Path(alias="tripId")],
    db: DbSession,
) -> TripDetailResponse:
    trip = TripService(db).get_trip(trip_id, detail=True)
    return _trip_detail_response(trip)


@router.patch(
    "/trips/{tripId}",
    response_model=TripResponse,
    responses={404: {"model": ErrorResponse}},
)
def update_trip(
    trip_id: Annotated[UUID, Path(alias="tripId")],
    payload: TripPatchRequest,
    db: DbSession,
) -> TripResponse:
    trip = TripService(db).update_trip(trip_id, payload.model_dump(exclude_unset=True))
    return _trip_response(trip)


@router.put(
    "/trips/{tripId}/hotel",
    response_model=HotelStayResponse,
    responses={404: {"model": ErrorResponse}},
)
def upsert_hotel(
    trip_id: Annotated[UUID, Path(alias="tripId")],
    payload: HotelStayRequest,
    db: DbSession,
) -> HotelStayResponse:
    hotel = TripService(db).upsert_hotel(trip_id, payload.model_dump())
    return _hotel_response(hotel)


@router.get(
    "/trips/{tripId}/hotel",
    response_model=HotelStayResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_hotel(
    trip_id: Annotated[UUID, Path(alias="tripId")],
    db: DbSession,
) -> HotelStayResponse:
    return _hotel_response(TripService(db).get_hotel(trip_id))


@router.get(
    "/trips/{tripId}/feed",
    response_model=TripFeedResponse,
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def trip_feed(
    trip_id: Annotated[UUID, Path(alias="tripId")],
    db: DbSession,
    settings: AppSettings,
    provider: RecommendationProviderDependency,
) -> TripFeedResponse:
    trip = TripService(db).get_trip(trip_id)
    result, context = await RecommendationService(
        db,
        provider,
        candidate_limit=settings.recommendation_max_candidates,
    ).recommend_for_trip(trip.id)
    logger.info(
        "trip_feed_completed trip_id=%s provider=%s recommendations=%d candidates=%d stores=%d",
        trip.id,
        type(provider).__name__,
        sum(len(store.products) for store in result.stores),
        len(context.candidate_products),
        len(context.candidate_stores),
    )
    return TripFeedResponse(
        trip=FeedTripResponse(id=trip.id, title=trip.title),
        recommendations=_feed_recommendations(result),
    )


@router.get(
    "/stores/{storeId}/wishlist-products",
    response_model=list[StoreWishlistProductResponse],
    responses={404: {"model": ErrorResponse}},
)
def store_wishlist_products(
    store_id: Annotated[UUID, Path(alias="storeId")],
    db: DbSession,
) -> list[StoreWishlistProductResponse]:
    return [
        StoreWishlistProductResponse(product_id=product.product_id, name=product.name)
        for product in TripService(db).list_store_wishlist_products(store_id)
    ]


@router.post(
    "/trips/{tripId}/visit-reservations",
    response_model=VisitReservationResponse,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def create_visit_reservation(
    trip_id: Annotated[UUID, Path(alias="tripId")],
    payload: VisitReservationCreateRequest,
    db: DbSession,
) -> VisitReservationResponse:
    reservation = TripService(db).create_reservation(
        trip_id,
        store_id=payload.store_id,
        scheduled_at=payload.scheduled_at,
        product_ids=payload.product_ids,
    )
    return _reservation_response(reservation)


@router.get(
    "/trips/{tripId}/visit-reservations",
    response_model=list[VisitReservationResponse],
    responses={404: {"model": ErrorResponse}},
)
def list_visit_reservations(
    trip_id: Annotated[UUID, Path(alias="tripId")],
    db: DbSession,
) -> list[VisitReservationResponse]:
    return [
        _reservation_response(reservation)
        for reservation in TripService(db).list_reservations(trip_id)
    ]


@router.delete(
    "/visit-reservations/{reservationId}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}},
)
def cancel_visit_reservation(
    reservation_id: Annotated[UUID, Path(alias="reservationId")],
    db: DbSession,
) -> Response:
    TripService(db).cancel_reservation(reservation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _trip_response(trip: Trip) -> TripResponse:
    return TripResponse(
        id=trip.id,
        title=trip.title,
        destination_city=trip.destination_city,
        destination_country=trip.destination_country,
        starts_at=trip.starts_at,
        ends_at=trip.ends_at,
        created_at=trip.created_at,
        updated_at=trip.updated_at,
    )


def _hotel_response(hotel: HotelStay) -> HotelStayResponse:
    return HotelStayResponse(
        id=hotel.id,
        trip_id=hotel.trip_id,
        name=hotel.name,
        address=hotel.address,
        latitude=hotel.latitude,
        longitude=hotel.longitude,
        check_in_at=hotel.check_in_at,
        check_out_at=hotel.check_out_at,
        created_at=hotel.created_at,
        updated_at=hotel.updated_at,
    )


def _flight_response(flight: Flight) -> FlightResponse:
    return FlightResponse(
        id=flight.id,
        trip_id=flight.trip_id,
        departure_airport=flight.departure_airport,
        arrival_airport=flight.arrival_airport,
        terminal=flight.terminal,
        flight_number=flight.flight_number,
        departure_at=flight.departure_at,
        arrival_at=flight.arrival_at,
        airport_arrival_at=flight.airport_arrival_at,
        created_at=flight.created_at,
    )


def _product_response(product: Product) -> ProductResponse:
    return ProductResponse(
        product_id=product.product_id,
        sku=product.sku,
        brand=product.brand,
        name=product.name,
        category=product.category,
        image_url=product.image_url,
    )


def _reservation_response(reservation: VisitReservation) -> VisitReservationResponse:
    return VisitReservationResponse(
        id=reservation.id,
        trip_id=reservation.trip_id,
        store=ReservationStoreResponse(
            store_id=reservation.store.id,
            name=reservation.store.name,
        ),
        scheduled_at=reservation.scheduled_at,
        products=[
            _product_response(item.product) for item in reservation.reservation_products
        ],
        status=reservation.status,
        created_at=reservation.created_at,
    )


def _trip_detail_response(trip: Trip) -> TripDetailResponse:
    return TripDetailResponse(
        trip=_trip_response(trip),
        flights=[
            _flight_response(flight)
            for flight in sorted(trip.flights, key=lambda item: (item.created_at, str(item.id)))
        ],
        hotel=_hotel_response(trip.hotel) if trip.hotel is not None else None,
        visit_reservations=[
            _reservation_response(reservation)
            for reservation in sorted(
                trip.visit_reservations,
                key=lambda item: (item.scheduled_at, str(item.id)),
            )
        ],
    )


def _feed_recommendations(result: RecommendationResult) -> list[FeedRecommendationResponse]:
    recommendations_by_product: dict[str, FeedRecommendationResponse] = {}
    for recommended_store in result.stores:
        for recommended_product in recommended_store.products:
            response = recommendations_by_product.get(recommended_product.product.product_id)
            if response is None:
                response = FeedRecommendationResponse(
                    product=_product_response(recommended_product.product),
                    reason=recommended_product.reason,
                    stores=[],
                )
                recommendations_by_product[recommended_product.product.product_id] = response
            response.stores.append(
                FeedStoreResponse(
                    store_id=recommended_store.store.id,
                    name=recommended_store.store.name,
                    type=recommended_store.store.type,
                    distance_from_hotel_km=recommended_store.distance_from_hotel_km,
                    airport_code=recommended_store.store.airport_code,
                    terminal=recommended_store.store.terminal,
                    has_wishlist_items=recommended_store.has_wishlist_items,
                    reason=recommended_store.reason,
                )
            )
    return list(recommendations_by_product.values())
