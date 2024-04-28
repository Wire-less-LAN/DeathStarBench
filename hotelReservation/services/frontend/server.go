package frontend

import (
	"encoding/json"
	"fmt"
	"net/http"
	"reflect"
	"strconv"

	"google.golang.org/grpc"

	recommendation "github.com/delimitrou/DeathStarBench/hotelreservation/services/recommendation/proto"
	reservation "github.com/delimitrou/DeathStarBench/hotelreservation/services/reservation/proto"
	user "github.com/delimitrou/DeathStarBench/hotelreservation/services/user/proto"
	"github.com/delimitrou/DeathStarBench/hotelreservation/unicomm"
	"github.com/rs/zerolog/log"

	"github.com/delimitrou/DeathStarBench/hotelreservation/dialer"
	retriever "github.com/delimitrou/DeathStarBench/hotelreservation/python/retriever/proto"
	"github.com/delimitrou/DeathStarBench/hotelreservation/registry"
	profile "github.com/delimitrou/DeathStarBench/hotelreservation/services/profile/proto"
	search "github.com/delimitrou/DeathStarBench/hotelreservation/services/search/proto"
	"github.com/delimitrou/DeathStarBench/hotelreservation/tls"
	"github.com/delimitrou/DeathStarBench/hotelreservation/tracing"
	"github.com/opentracing/opentracing-go"
)

// Server implements frontend service
type Server struct {
	searchClient            search.SearchClient
	uniSearchClient         unicomm.UniClient
	profileClient           profile.ProfileClient
	uniProfileClient        unicomm.UniClient
	recommendationClient    recommendation.RecommendationClient
	uniRecommendationClient unicomm.UniClient
	userClient              user.UserClient
	uniUserClient           unicomm.UniClient
	reservationClient       reservation.ReservationClient
	uniReservationClient    unicomm.UniClient
	uniRetrieverClient      unicomm.UniClient
	KnativeDns              string
	IpAddr                  string
	Port                    int
	Tracer                  opentracing.Tracer
	Registry                *registry.Client
}

// Run the server
func (s *Server) Run() error {
	if s.Port == 0 {
		return fmt.Errorf("Server port must be set")
	}

	log.Info().Msg("Initializing gRPC clients...")
	err := *new(error)
	if s.uniSearchClient, err = unicomm.InitUniClient("frontend", "search", "srv-search", "/search.Search/", s.KnativeDns, &s.Tracer, s.Registry); err != nil {
		return err
	}
	if s.uniProfileClient, err = unicomm.InitUniClient("frontend", "profile", "srv-profile", "/profile.Profile/", s.KnativeDns, &s.Tracer, s.Registry); err != nil {
		return err
	}
	if s.uniRecommendationClient, err = unicomm.InitUniClient("frontend", "recommendation", "srv-recommendation", "/recommendation.Recommendation/", s.KnativeDns, &s.Tracer, s.Registry); err != nil {
		return err
	}
	if s.uniUserClient, err = unicomm.InitUniClient("frontend", "user", "srv-user", "/user.User/", s.KnativeDns, &s.Tracer, s.Registry); err != nil {
		return err
	}
	if s.uniReservationClient, err = unicomm.InitUniClient("frontend", "reservation", "srv-reservation", "/reservation.Reservation/", s.KnativeDns, &s.Tracer, s.Registry); err != nil {
		return err
	}
	if s.uniRetrieverClient, err = unicomm.InitUniClient("frontend", "retriever", "srv-retriever", "/Retriever/", s.KnativeDns, &s.Tracer, s.Registry); err != nil {
		return err
	}

	// if err := s.initProfileClient("srv-profile"); err != nil {
	// 	return err
	// }

	// if err := s.initRecommendationClient("srv-recommendation"); err != nil {
	// 	return err
	// }

	// if err := s.initUserClient("srv-user"); err != nil {
	// 	return err
	// }

	// if err := s.initReservation("srv-reservation"); err != nil {
	// 	return err
	// }
	log.Info().Msg("Successfull")

	log.Trace().Msg("frontend before mux")
	mux := tracing.NewServeMux(s.Tracer)
	mux.Handle("/", http.FileServer(http.Dir("services/frontend/static")))
	mux.Handle("/hotels", http.HandlerFunc(s.searchHandler))
	mux.Handle("/recommendations", http.HandlerFunc(s.recommendHandler))
	mux.Handle("/user", http.HandlerFunc(s.userHandler))
	mux.Handle("/reservation", http.HandlerFunc(s.reservationHandler))
	mux.Handle("/query", http.HandlerFunc(s.queryHandler))

	log.Trace().Msg("frontend starts serving")

	tlsconfig := tls.GetHttpsOpt()
	srv := &http.Server{
		Addr:    fmt.Sprintf(":%d", s.Port),
		Handler: mux,
	}
	if tlsconfig != nil {
		log.Info().Msg("Serving https")
		srv.TLSConfig = tlsconfig
		return srv.ListenAndServeTLS("x509/server_cert.pem", "x509/server_key.pem")
	} else {
		log.Info().Msg("Serving http")
		return srv.ListenAndServe()
	}
}

func (s *Server) initSearchClient(name string) error {
	conn, err := s.getGprcConn(name)
	if err != nil {
		return fmt.Errorf("dialer error: %v", err)
	}
	s.searchClient = search.NewSearchClient(conn)
	return nil
}

func (s *Server) initProfileClient(name string) error {
	conn, err := s.getGprcConn(name)
	if err != nil {
		return fmt.Errorf("dialer error: %v", err)
	}
	s.profileClient = profile.NewProfileClient(conn)
	return nil
}

func (s *Server) initRecommendationClient(name string) error {
	conn, err := s.getGprcConn(name)
	if err != nil {
		return fmt.Errorf("dialer error: %v", err)
	}
	s.recommendationClient = recommendation.NewRecommendationClient(conn)
	return nil
}

func (s *Server) initUserClient(name string) error {
	conn, err := s.getGprcConn(name)
	if err != nil {
		return fmt.Errorf("dialer error: %v", err)
	}
	s.userClient = user.NewUserClient(conn)
	return nil
}

func (s *Server) initReservation(name string) error {
	conn, err := s.getGprcConn(name)
	if err != nil {
		return fmt.Errorf("dialer error: %v", err)
	}
	s.reservationClient = reservation.NewReservationClient(conn)
	return nil
}

func (s *Server) getGprcConn(name string) (*grpc.ClientConn, error) {
	log.Info().Msg("get Grpc conn is :")
	log.Info().Msg(s.KnativeDns)
	log.Info().Msg(fmt.Sprintf("%s.%s", name, s.KnativeDns))
	if s.KnativeDns != "" {
		return dialer.Dial(
			fmt.Sprintf("%s.%s", name, s.KnativeDns),
			dialer.WithTracer(s.Tracer))
	} else {
		return dialer.Dial(
			name,
			dialer.WithTracer(s.Tracer),
			dialer.WithBalancer(s.Registry.Client),
		)
	}
}

func (s *Server) queryHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	ctx := r.Context()

	log.Trace().Msg("starts queryHandler")

	// prompt from params
	method := r.URL.Query().Get("method")
	if method == "" {
		http.Error(w, "Please specify method", http.StatusBadRequest)
		return
	}
	prompt := r.URL.Query().Get("prompt")
	if prompt == "" {
		http.Error(w, "Please specify prompt", http.StatusBadRequest)
		return
	}
	log.Trace().Msg("starts queryHandler querying downstream")

	if method == "query" {
		log.Trace().Msgf("RETRIEVER QUERY [prompt: %v]", prompt)
		tmp, err := s.uniRetrieverClient.Call(ctx, "Query", &retriever.Request{
			Prompt: prompt,
		}, reflect.TypeFor[retriever.Result]())
		if err != nil {
			log.Error().Msgf("Retriever.Query failed: %s", err.Error())
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		resp, ok := tmp.(*retriever.Result)
		if !ok {
			log.Error().Msgf("failed to convert retriever.Query's resp")
			http.Error(w, "failed to convert retriever.Query's resp", http.StatusInternalServerError)
			return
		}

		log.Info().Msg("QueryHandler got resp")

		json.NewEncoder(w).Encode(map[string]interface{}{"resp": resp.NewPrompt})
	} else if method == "search" {
		log.Trace().Msgf("RETRIEVER SEARCH [prompt: %v]", prompt)
		tmp, err := s.uniRetrieverClient.Call(ctx, "Search", &retriever.Request{
			Prompt: prompt,
		}, reflect.TypeFor[retriever.Result]())
		if err != nil {
			log.Error().Msgf("Retriever.Search failed: %s", err.Error())
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		resp, ok := tmp.(*retriever.Result)
		if !ok {
			log.Error().Msgf("failed to convert retriever.Search's resp")
			http.Error(w, "failed to convert retriever.Search's resp", http.StatusInternalServerError)
			return
		}

		log.Info().Msg("QueryHandler got resp")

		json.NewEncoder(w).Encode(map[string]interface{}{"resp": resp.NewPrompt})
	} else {
		http.Error(w, "Invalid method", http.StatusBadRequest)
		return
	}
}

func (s *Server) searchHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	ctx := r.Context()

	log.Trace().Msg("starts searchHandler")

	// in/out dates from query params
	inDate, outDate := r.URL.Query().Get("inDate"), r.URL.Query().Get("outDate")
	if inDate == "" || outDate == "" {
		http.Error(w, "Please specify inDate/outDate params", http.StatusBadRequest)
		return
	}

	// lan/lon from query params
	sLat, sLon := r.URL.Query().Get("lat"), r.URL.Query().Get("lon")
	if sLat == "" || sLon == "" {
		http.Error(w, "Please specify location params", http.StatusBadRequest)
		return
	}

	Lat, _ := strconv.ParseFloat(sLat, 32)
	lat := float32(Lat)
	Lon, _ := strconv.ParseFloat(sLon, 32)
	lon := float32(Lon)

	log.Trace().Msg("starts searchHandler querying downstream")

	log.Trace().Msgf("SEARCH [lat: %v, lon: %v, inDate: %v, outDate: %v", lat, lon, inDate, outDate)
	//search for best hotels
	// searchResp, err := s.searchClient.Nearby(ctx, &search.NearbyRequest{
	// 	Lat:     lat,
	// 	Lon:     lon,
	// 	InDate:  inDate,
	// 	OutDate: outDate,
	// })
	tmp, err := s.uniSearchClient.Call(ctx, "Nearby", &search.NearbyRequest{
		Lat:     lat,
		Lon:     lon,
		InDate:  inDate,
		OutDate: outDate,
	}, reflect.TypeFor[search.SearchResult]())
	if err != nil {
		log.Error().Msgf("Search.Nearby failed: %s", err.Error())
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	searchResp, ok := tmp.(*search.SearchResult)
	if !ok {
		log.Error().Msgf("failed to convert search.Nearby's resp")
		http.Error(w, "failed to convert search.Nearby's resp", http.StatusInternalServerError)
		return
	}

	log.Info().Msg("SearchHandler gets searchResp")
	//for _, hid := range searchResp.HotelIds {
	//	log.Trace().Msgf("Search Handler hotelId = %s", hid)
	//}

	// grab locale from query params or default to en
	locale := r.URL.Query().Get("locale")
	if locale == "" {
		locale = "en"
	}

	// reservationResp, err := s.reservationClient.CheckAvailability(ctx, &reservation.Request{
	// 	CustomerName: "",
	// 	HotelId:      searchResp.HotelIds,
	// 	InDate:       inDate,
	// 	OutDate:      outDate,
	// 	RoomNumber:   1,
	// })
	tmp, err = s.uniReservationClient.Call(ctx, "CheckAvailability", &reservation.Request{
		CustomerName: "",
		HotelId:      searchResp.HotelIds,
		InDate:       inDate,
		OutDate:      outDate,
		RoomNumber:   1,
	}, reflect.TypeFor[reservation.Result]())
	if err != nil {
		log.Error().Msg("SearchHandler CheckAvailability failed")
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	reservationResp, ok := tmp.(*reservation.Result)
	if !ok {
		log.Error().Msg("failed to convert reservation.CheckAvailability's resp")
		http.Error(w, "failed to convert reservation.CheckAvailability's resp", http.StatusInternalServerError)
		return

	}

	log.Trace().Msgf("searchHandler gets reserveResp")
	log.Trace().Msgf("searchHandler gets reserveResp.HotelId = %s", reservationResp.HotelId)

	// hotel profiles
	// profileResp, err := s.profileClient.GetProfiles(ctx, &profile.Request{
	// 	HotelIds: reservationResp.HotelId,
	// 	Locale:   locale,
	// })
	tmp, err = s.uniProfileClient.Call(ctx, "GetProfiles", &profile.Request{
		HotelIds: reservationResp.HotelId,
		Locale:   locale,
	}, reflect.TypeFor[profile.Result]())
	if err != nil {
		log.Error().Msg("SearchHandler GetProfiles failed")
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	profileResp, ok := tmp.(*profile.Result)
	if !ok {
		log.Error().Msg("failed to convert profile.GetProfiles' resp")
		http.Error(w, "failed to convert profile.GetProfiles' resp", http.StatusInternalServerError)
		return
	}

	log.Trace().Msg("searchHandler gets profileResp")

	json.NewEncoder(w).Encode(geoJSONResponse(profileResp.Hotels))
}

func (s *Server) recommendHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	ctx := r.Context()

	sLat, sLon := r.URL.Query().Get("lat"), r.URL.Query().Get("lon")
	if sLat == "" || sLon == "" {
		http.Error(w, "Please specify location params", http.StatusBadRequest)
		return
	}
	Lat, _ := strconv.ParseFloat(sLat, 64)
	lat := float64(Lat)
	Lon, _ := strconv.ParseFloat(sLon, 64)
	lon := float64(Lon)

	require := r.URL.Query().Get("require")
	if require != "dis" && require != "rate" && require != "price" {
		http.Error(w, "Please specify require params", http.StatusBadRequest)
		return
	}

	// recommend hotels
	// recResp, err := s.recommendationClient.GetRecommendations(ctx, &recommendation.Request{
	// 	Require: require,
	// 	Lat:     float64(lat),
	// 	Lon:     float64(lon),
	// })
	tmp, err := s.uniRecommendationClient.Call(ctx, "GetRecommendations", &recommendation.Request{
		Require: require,
		Lat:     float64(lat),
		Lon:     float64(lon),
	}, reflect.TypeFor[recommendation.Result]())
	if err != nil {
		log.Error().Msg("RecommendHandler GetRecommendations failed")
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	recResp, ok := tmp.(*recommendation.Result)
	if !ok {
		log.Error().Msg("failed to convert recommendation.GetRecommendations' resp")
		http.Error(w, "failed to convert recommendation.GetRecommendations' resp", http.StatusInternalServerError)
		return
	}

	// grab locale from query params or default to en
	locale := r.URL.Query().Get("locale")
	if locale == "" {
		locale = "en"
	}

	// hotel profiles
	// profileResp, err := s.profileClient.GetProfiles(ctx, &profile.Request{
	// 	HotelIds: recResp.HotelIds,
	// 	Locale:   locale,
	// })
	tmp, err = s.uniProfileClient.Call(ctx, "GetProfiles", &profile.Request{
		HotelIds: recResp.HotelIds,
		Locale:   locale,
	}, reflect.TypeFor[profile.Result]())
	if err != nil {
		log.Error().Msg("RecommendHandler GetProfiles failed")
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	profileResp, ok := tmp.(*profile.Result)
	if !ok {
		log.Error().Msg("failed to convert profile.GetProfiles' resp")
		http.Error(w, "failed to convert profile.GetProfiles' resp", http.StatusInternalServerError)
		return
	}

	json.NewEncoder(w).Encode(geoJSONResponse(profileResp.Hotels))
}

func (s *Server) userHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	ctx := r.Context()

	username, password := r.URL.Query().Get("username"), r.URL.Query().Get("password")
	if username == "" || password == "" {
		http.Error(w, "Please specify username and password", http.StatusBadRequest)
		return
	}

	// Check username and password
	// recResp, err := s.userClient.CheckUser(ctx, &user.Request{
	// 	Username: username,
	// 	Password: password,
	// })
	tmp, err := s.uniUserClient.Call(ctx, "CheckUser", &user.Request{
		Username: username,
		Password: password,
	}, reflect.TypeFor[user.Result]())
	if err != nil {
		log.Error().Msg("UserHandler CheckUser failed")
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	recResp, ok := tmp.(*user.Result)
	if !ok {
		log.Error().Msg("failed to convert user.CheckUser resp")
		http.Error(w, "failed to convert user.CheckUser resp", http.StatusInternalServerError)
		return
	}

	str := "Login successfully!"
	if !recResp.Correct {
		str = "Failed. Please check your username and password. "
	}

	res := map[string]interface{}{
		"message": str,
	}

	json.NewEncoder(w).Encode(res)
}

func (s *Server) reservationHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	ctx := r.Context()

	inDate, outDate := r.URL.Query().Get("inDate"), r.URL.Query().Get("outDate")
	if inDate == "" || outDate == "" {
		http.Error(w, "Please specify inDate/outDate params", http.StatusBadRequest)
		return
	}

	if !checkDataFormat(inDate) || !checkDataFormat(outDate) {
		http.Error(w, "Please check inDate/outDate format (YYYY-MM-DD)", http.StatusBadRequest)
		return
	}

	hotelId := r.URL.Query().Get("hotelId")
	if hotelId == "" {
		http.Error(w, "Please specify hotelId params", http.StatusBadRequest)
		return
	}

	customerName := r.URL.Query().Get("customerName")
	if customerName == "" {
		http.Error(w, "Please specify customerName params", http.StatusBadRequest)
		return
	}

	username, password := r.URL.Query().Get("username"), r.URL.Query().Get("password")
	if username == "" || password == "" {
		http.Error(w, "Please specify username and password", http.StatusBadRequest)
		return
	}

	numberOfRoom := 0
	num := r.URL.Query().Get("number")
	if num != "" {
		numberOfRoom, _ = strconv.Atoi(num)
	}

	// Check username and password
	tmp, err := s.uniUserClient.Call(ctx, "CheckUser", &user.Request{
		Username: username,
		Password: password,
	}, reflect.TypeFor[user.Result]())
	if err != nil {
		log.Error().Msg("UserHandler CheckUser failed")
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	recResp, ok := tmp.(*user.Result)
	if !ok {
		log.Error().Msg("failed to convert user.CheckUser resp")
		http.Error(w, "failed to convert user.CheckUser resp", http.StatusInternalServerError)
		return
	}

	str := "Reserve successfully!"
	if !recResp.Correct {
		str = "Failed. Please check your username and password. "
	}

	// Make reservation
	tmp, err = s.uniReservationClient.Call(ctx, "MakeReservation", &reservation.Request{
		CustomerName: customerName,
		HotelId:      []string{hotelId},
		InDate:       inDate,
		OutDate:      outDate,
		RoomNumber:   int32(numberOfRoom),
	}, reflect.TypeFor[reservation.Result]())
	if err != nil {
		log.Error().Msg("reservationHandler MakeReservation failed")
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	resResp, ok := tmp.(*reservation.Result)
	if !ok {
		log.Error().Msg("failed to convert reservation.MakeReservation resp")
		http.Error(w, "failed to convert reservation.MakeReservation resp", http.StatusInternalServerError)
		return

	}

	// resResp, err := s.reservationClient.MakeReservation(ctx, &reservation.Request{
	// 	CustomerName: customerName,
	// 	HotelId:      []string{hotelId},
	// 	InDate:       inDate,
	// 	OutDate:      outDate,
	// 	RoomNumber:   int32(numberOfRoom),
	// })

	if len(resResp.HotelId) == 0 {
		str = "Failed. Already reserved. "
	}

	res := map[string]interface{}{
		"message": str,
	}

	json.NewEncoder(w).Encode(res)
}

// return a geoJSON response that allows google map to plot points directly on map
// https://developers.google.com/maps/documentation/javascript/datalayer#sample_geojson
func geoJSONResponse(hs []*profile.Hotel) map[string]interface{} {
	fs := []interface{}{}

	for _, h := range hs {
		fs = append(fs, map[string]interface{}{
			"type": "Feature",
			"id":   h.Id,
			"properties": map[string]string{
				"name":         h.Name,
				"phone_number": h.PhoneNumber,
			},
			"geometry": map[string]interface{}{
				"type": "Point",
				"coordinates": []float32{
					h.Address.Lon,
					h.Address.Lat,
				},
			},
		})
	}

	return map[string]interface{}{
		"type":     "FeatureCollection",
		"features": fs,
	}
}

func checkDataFormat(date string) bool {
	if len(date) != 10 {
		return false
	}
	for i := 0; i < 10; i++ {
		if i == 4 || i == 7 {
			if date[i] != '-' {
				return false
			}
		} else {
			if date[i] < '0' || date[i] > '9' {
				return false
			}
		}
	}
	return true
}
