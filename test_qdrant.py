import os
from qdrant_client import QdrantClient

url = "https://5363ae74-c776-46dc-b597-2d1fdef6317d.sa-east-1-0.aws.cloud.qdrant.io"
api_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.G30Q6LBEUw3zWUQbAxp1Vf93gJpkfKhymHkqZYajm4s"
try:
    print("Testing standard URL port 6333")
    client = QdrantClient(url=url+":6333", api_key=api_key)
    print(client.get_collections())
except Exception as e:
    print("Error 6333:", e)

try:
    print("Testing standard URL port 443")
    client = QdrantClient(url=url, api_key=api_key)
    print(client.get_collections())
except Exception as e:
    print("Error 443:", e)

try:
    print("Testing URL without https")
    client = QdrantClient(host="5363ae74-c776-46dc-b597-2d1fdef6317d.sa-east-1-0.aws.cloud.qdrant.io", port=6333, https=True, api_key=api_key)
    print(client.get_collections())
except Exception as e:
    print("Error host:", e)
