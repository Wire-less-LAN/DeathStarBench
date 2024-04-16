package unicomm

import (
	"context"
	"fmt"
	"net"
	"os"
	"reflect"

	"github.com/delimitrou/DeathStarBench/hotelreservation/dialer"
	"github.com/delimitrou/DeathStarBench/hotelreservation/registry"
	redis "github.com/go-redis/redis/v8"
	"github.com/opentracing/opentracing-go"
	"github.com/rs/zerolog/log"

	"google.golang.org/grpc"
)

type RegisterFuncType[S any] func(*grpc.Server, S)

func NewUnixSocket(socketPath string) (net.Listener, error) {
	if err := os.Remove(socketPath); err != nil && !os.IsNotExist(err) {
		return nil, err
	}

	lis, err := net.Listen("unix", socketPath)
	if err != nil {
		return nil, err
	}

	return lis, nil
}

type HRServer[S any] struct {
	Name       string
	Uuid       string
	Port       int
	IpAddr     string
	SocketPath string

	Registry *registry.Client
	Register RegisterFuncType[S]

	Server S
}

func (s *HRServer[S]) RunServers(opts ...grpc.ServerOption) error {
	srv := grpc.NewServer(opts...)
	unixSrv := grpc.NewServer(opts...)

	s.Register(srv, s.Server)
	s.Register(unixSrv, s.Server)

	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", s.Port))
	if err != nil {
		return fmt.Errorf("failed to listen: %v", err)
	}

	err = s.Registry.Register(s.Name, s.Uuid, s.IpAddr, s.Port)
	if err != nil {
		return fmt.Errorf("failed register: %v", err)
	}
	log.Info().Msg("Successfully registered in consul")

	unixLis, err := NewUnixSocket(s.SocketPath)
	if err != nil {
		return fmt.Errorf("failed to listen: %v", err)
	}

	errChan := make(chan error, 2)

	go func() {
		if err := srv.Serve(lis); err != nil {
			errChan <- err
		}
	}()
	go func() {
		if err := unixSrv.Serve(unixLis); err != nil {
			errChan <- err
		}
	}()

	return <-errChan
}

type CommType int

const (
	INTERNODE CommType = iota
	INTERCPU
	INTERGPU
	INTRAGPU
)

func GetCommType(srv_a string, srv_b string) (CommType, error) {
	rdb := redis.NewClient(&redis.Options{
		Network:  "unix",
		Addr:     "/var/run/redis/redis.sock",
		Password: "",
		DB:       0,
	})
	defer rdb.Close()
	redis_ctx := context.Background()

	a_loc, err := rdb.Get(redis_ctx, srv_a).Result()
	if err != nil {
		return -1, err
	}
	b_loc, err := rdb.Get(redis_ctx, srv_b).Result()
	if err != nil {
		return -1, err
	}

	if a_loc == b_loc { //TODO: inter-gpu, intra-gpu
		return INTERCPU, nil
	} else {
		return INTERNODE, nil
	}
}

type UniClient struct {
	cmdName    string
	tgtCmdName string
	funcPrefix string
	conn       *grpc.ClientConn
	unixConn   *grpc.ClientConn
}

func InitUniClient(cmdName string, tgtCmdName string, tgtSrvName string, funcPrefix string, knativeDns string, tracer *opentracing.Tracer, rc *registry.Client) (UniClient, error) {
	conn := new(grpc.ClientConn)
	err := *new(error)

	if knativeDns != "" {
		conn, err = dialer.Dial(
			fmt.Sprintf("%s.%s", tgtSrvName, knativeDns),
			dialer.WithTracer(*tracer))
	} else {
		conn, err = dialer.Dial(
			tgtSrvName,
			dialer.WithTracer(*tracer),
			dialer.WithBalancer(rc.Client),
		)
	}
	if err != nil {
		return UniClient{}, fmt.Errorf("dialer error: %v", err)
	}

	unixConn, err := dialer.Dial("unix:///var/run/hrsock/"+tgtCmdName+".sock", dialer.WithTracer(*tracer))
	if err != nil {
		return UniClient{}, fmt.Errorf("dialer error: %v", err)
	}

	return UniClient{cmdName,
		tgtCmdName,
		funcPrefix,
		conn,
		unixConn}, nil
}

func (c *UniClient) Call(ctx context.Context, funcName string, in interface{}, respType reflect.Type, opts ...grpc.CallOption) (interface{}, error) {
	out := reflect.New(respType).Interface()

	commType, err := GetCommType(c.cmdName, c.tgtCmdName)
	if err != nil {
		return nil, err
	}

	switch commType {
	case INTERNODE:
		err := grpc.Invoke(ctx, c.funcPrefix+funcName, in, out, c.conn, opts...)
		if err != nil {
			return nil, err
		}
		break

	case INTERCPU:
		// send through unix socket
		err := grpc.Invoke(ctx, c.funcPrefix+funcName, in, out, c.unixConn, opts...)
		if err != nil {
			return nil, err
		}
		break

	case INTERGPU:
	case INTRAGPU:
		//TODO
		break
	}

	return out, nil
}

// type uniSearchClient struct {
// 	real_client *search_pb.SearchClient
// 	srv_name    string
// }

// func (c *uniSearchClient) Nearby(ctx context.Context, in *search_pb.NearbyRequest, opts ...grpc.CallOption) (*search_pb.SearchResult, error) {
// 	out := new(search_pb.SearchResult)

// 	comm_type, err := GetCommType(c.srv_name, "search")
// 	if err != nil {
// 		return nil, err
// 	}

// 	switch comm_type {
// 	case INTERNODE:
// 		err := grpc.Invoke(ctx, "/search.Search/Nearby", in, out, c.cc, opts...)
// 		if err != nil {
// 			return nil, err
// 		}
// 		break

// 	case INTERCPU:
// 		// send through unix socket
// 		break
// 	}
// 	return out, nil
// }

// func main() {
//     // Unix套接字路径
//     socketPath := "/container/socket/mysocket.sock"

//     // 监听Unix套接字
//     ln, err := net.Listen("unix", socketPath)
//     if err != nil {
//         log.Fatalf("Error listening on socket: %v", err)
//     }
//     defer ln.Close()

//     fmt.Println("Listening on", socketPath)
//     for {
//         // 接受连接
//         conn, err := ln.Accept()
//         if err != nil {
//             log.Printf("Error accepting connection: %v", err)
//             continue
//         }

//         // 处理连接
//         go handleConnection(conn)
//     }
// }

// func handleConnection(conn net.Conn) {
//     defer conn.Close()

//     // 读取Protobuf消息
//     buf := make([]byte, 1024) // 根据消息大小调整缓冲区大小
//     n, err := conn.Read(buf)
//     if err != nil {
//         if err != io.EOF {
//             log.Printf("Error reading message: %v", err)
//         }
//         return
//     }

//     // 反序列化Protobuf消息
//     var msg package.MyMessage // 使用正确的消息类型
//     err = proto.Unmarshal(buf[:n], &msg)
//     if err != nil {
//         log.Printf("Error unmarshalling message: %v", err)
//         return
//     }

//     fmt.Printf("Received message: %s\n", msg.Content)
// }
