# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: services/geo/proto/geo.proto
# Protobuf Python Version: 4.25.1
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x1cservices/geo/proto/geo.proto\x12\x03geo\"#\n\x07Request\x12\x0b\n\x03lat\x18\x01 \x01(\x02\x12\x0b\n\x03lon\x18\x02 \x01(\x02\"\x1a\n\x06Result\x12\x10\n\x08hotelIds\x18\x01 \x03(\t2*\n\x03Geo\x12#\n\x06Nearby\x12\x0c.geo.Request\x1a\x0b.geo.Resultb\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'services.geo.proto.geo_pb2', _globals)
if _descriptor._USE_C_DESCRIPTORS == False:
  DESCRIPTOR._options = None
  _globals['_REQUEST']._serialized_start=37
  _globals['_REQUEST']._serialized_end=72
  _globals['_RESULT']._serialized_start=74
  _globals['_RESULT']._serialized_end=100
  _globals['_GEO']._serialized_start=102
  _globals['_GEO']._serialized_end=144
# @@protoc_insertion_point(module_scope)