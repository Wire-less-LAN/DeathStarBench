# Generated by the gRPC Python protocol compiler plugin. DO NOT EDIT!
"""Client and server classes corresponding to protobuf-defined services."""
import grpc

from services.reservation.proto import reservation_pb2 as services_dot_reservation_dot_proto_dot_reservation__pb2


class ReservationStub(object):
    """Missing associated documentation comment in .proto file."""

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.MakeReservation = channel.unary_unary(
                '/reservation.Reservation/MakeReservation',
                request_serializer=services_dot_reservation_dot_proto_dot_reservation__pb2.Request.SerializeToString,
                response_deserializer=services_dot_reservation_dot_proto_dot_reservation__pb2.Result.FromString,
                )
        self.CheckAvailability = channel.unary_unary(
                '/reservation.Reservation/CheckAvailability',
                request_serializer=services_dot_reservation_dot_proto_dot_reservation__pb2.Request.SerializeToString,
                response_deserializer=services_dot_reservation_dot_proto_dot_reservation__pb2.Result.FromString,
                )


class ReservationServicer(object):
    """Missing associated documentation comment in .proto file."""

    def MakeReservation(self, request, context):
        """MakeReservation makes a reservation based on given information
        """
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CheckAvailability(self, request, context):
        """CheckAvailability checks if given information is available
        """
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')


def add_ReservationServicer_to_server(servicer, server):
    rpc_method_handlers = {
            'MakeReservation': grpc.unary_unary_rpc_method_handler(
                    servicer.MakeReservation,
                    request_deserializer=services_dot_reservation_dot_proto_dot_reservation__pb2.Request.FromString,
                    response_serializer=services_dot_reservation_dot_proto_dot_reservation__pb2.Result.SerializeToString,
            ),
            'CheckAvailability': grpc.unary_unary_rpc_method_handler(
                    servicer.CheckAvailability,
                    request_deserializer=services_dot_reservation_dot_proto_dot_reservation__pb2.Request.FromString,
                    response_serializer=services_dot_reservation_dot_proto_dot_reservation__pb2.Result.SerializeToString,
            ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
            'reservation.Reservation', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))


 # This class is part of an EXPERIMENTAL API.
class Reservation(object):
    """Missing associated documentation comment in .proto file."""

    @staticmethod
    def MakeReservation(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/reservation.Reservation/MakeReservation',
            services_dot_reservation_dot_proto_dot_reservation__pb2.Request.SerializeToString,
            services_dot_reservation_dot_proto_dot_reservation__pb2.Result.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def CheckAvailability(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/reservation.Reservation/CheckAvailability',
            services_dot_reservation_dot_proto_dot_reservation__pb2.Request.SerializeToString,
            services_dot_reservation_dot_proto_dot_reservation__pb2.Result.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)
