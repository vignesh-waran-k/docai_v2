import os
import json
import concurrent.futures
import urllib.request
import pandas as pd
import re
from datetime import datetime
from google.api_core.client_options import ClientOptions
from google.api_core.exceptions import InternalServerError, RetryError
from google.cloud import documentai, storage
from google.cloud import firestore


"""
project_name          = 'xx-xx-xx'
input_bucket_name     = 'xx-db-test'  #'xx_shell_input'
project_id            = 'xxxxxx'
location              = 'us'
processor_id          = 'xxx6fxxec5xx'
gcs_output_uri_prefix = 'daira_outputs'
"""

input_bucket_name     = 'daira_shell_input' 
gcs_output_uri_prefix = 'daira_outputs'

# read the config data
storage_client = storage.Client()
bucket = storage_client.bucket(input_bucket_name)
blob = bucket.blob('config/config.txt') #gs://daira-db-test/config/config.txt
config_data = blob.download_as_string().decode('utf-8')

print(str(config_data).split('\n'))

input_parameters = str(config_data).split('\n')
project_name = input_parameters[0].split(':')[1].strip()
location = input_parameters[2].split(':')[1].strip()
processor_id = input_parameters[6].split('/')[-1]
project_id = input_parameters[6].split('/')[1]

print('input_bucket_name ', input_bucket_name)
print('project_name ', project_name)
print('location ', location)
print('processor_id ', processor_id)
print('project_id ', project_id)

metadata_array = []

connection = firestore.Client(project = project_name)


def list_blobs(bucket_name):
        print("list_blobs")
        storage_client = storage.Client()
        blobs          = storage_client.list_blobs(bucket_name)
        blob_arr       = []
        for blob in blobs:
            blob_arr.append(blob.name)
        return blob_arr




def delete_blob(bucket_name, blob_name):
        print("delete_blob")
        storage_client = storage.Client()
        bucket         = storage_client.bucket(bucket_name)
        blob           = bucket.blob(blob_name)
        try:
            blob.delete()
        except:
            pass




def bucket_cleaner(bucket_name):
    print("bucket_cleaner")
    bucket_blobs_list = list_blobs(bucket_name)
    for i in bucket_blobs_list:
        delete_blob(bucket_name, i)




def copy_blob(bucket_name, blob_name, destination_bucket_name, destination_blob_name):
        print("copy_blob")
        storage_client     = storage.Client()
        source_bucket      = storage_client.bucket(bucket_name)
        source_blob        = source_bucket.blob(blob_name)
        destination_bucket = storage_client.bucket(destination_bucket_name)
        blob_copy          = source_bucket.copy_blob(source_blob, destination_bucket, destination_blob_name)
        print("*/tstorage_client : ",storage_client)
        print("*/tsource_bucket : ",source_bucket)
        print("*/tsource_blob : ",source_blob)
        print("*/tdestination_bucket : ",destination_bucket)
        print("*/tblob_copy : ",blob_copy)




def db_insert(info_list_holder):
        print("db_insert")
        global connection
        for i in info_list_holder:
            for j in i:
                file_name     = j['filename']
                doc_reference = connection.collection(u'daira_logs').document(file_name)
                doc_reference.set(j)




def db_print():
        print("db_print")
        global connection
        db_entries = []
        reference  = connection.collection(u'daira_logs')
        docs       = reference.stream()
        for doc in docs:
            db_entries.append(doc.to_dict())
        db_dataframe = pd.DataFrame(db_entries)
        return db_dataframe




def bucket_lister(bucket_name):
        print("bucket_lister")
        storage_client = storage.Client()
        blobs = storage_client.list_blobs(bucket_name)
        blob_arr = []
        for blob in blobs:
            blob_arr.append('gs://'+bucket_name+'/'+blob.name)
        return blob_arr




def create_bucket_class_location(bucket_name):        
        print("create_bucket_class_location")
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        new_bucket = storage_client.create_bucket(bucket, location="us")
        print("Bucket Created successfully : ", bucket_name)



def batch_process_documents(
    project_id,
    location,
    processor_id,
    gcs_input_uri,
    gcs_output_uri,
    gcs_output_uri_prefix,
    timeout: int = 600,
    ):
        print("batch_process_documents : ")
        print(gcs_input_uri, gcs_output_uri, gcs_output_uri_prefix)
        from google.cloud import documentai_v1beta3 as documentai
        opts = {}
        if location == "eu":
            opts = {"api_endpoint": "eu-documentai.googleapis.com"}
        elif location == "us":
            opts = {"api_endpoint": "us-documentai.googleapis.com"}
        client = documentai.DocumentProcessorServiceClient(client_options=opts)
        destination_uri = f"{gcs_output_uri}/{gcs_output_uri_prefix}/"
        input_config= documentai.BatchDocumentsInputConfig(gcs_prefix=documentai.GcsPrefix(gcs_uri_prefix=gcs_input_uri))
        output_config = documentai.DocumentOutputConfig(gcs_output_config={"gcs_uri": destination_uri})
        name = f"projects/{project_id}/locations/{location}/processors/{processor_id}"
        request = documentai.types.document_processor_service.BatchProcessRequest(name=name, input_documents=input_config, document_output_config=output_config,)
        operation = client.batch_process_documents(request)
        print("<<< OPERATION >>>")
        print(operation.operation) #details fr a single batch of files
        operation.result(timeout=timeout)
        metadata = documentai.BatchProcessMetadata(operation.metadata)
        return metadata



def batch_caller(gcs_input_uri, gcs_output_uri):
        print("batch_caller:")
        print(gcs_input_uri, gcs_output_uri)
        global project_id
        global location
        global processor_id
        global gcs_output_uri_prefix
        global metadata_array
        print("BATCH_CALLER project_id : ",project_id)
        recived_metadata = batch_process_documents(project_id, location, processor_id, gcs_input_uri, gcs_output_uri, gcs_output_uri_prefix)
        metadata_array.append(recived_metadata)




def metadata_reader(metadata):
        print("metadata_reader")
        info_array = []
        metadata_ips = metadata.individual_process_statuses
        metadata_state = metadata.state.name
        metadata_createtime = metadata.create_time.ctime()
        metadata_updatetime = metadata.update_time.ctime()
        for i in metadata_ips:
            info_array.append({
                'filename' : i.input_gcs_source.split('/')[-1],
                'metadata_state' : metadata_state,
                'metadata_createtime' : metadata_createtime,
                'metadata_updatetime' : metadata_updatetime,
                'operation_id' : i.output_gcs_destination.split('/')[-2],
                'file_output_gcs_destination' : i.output_gcs_destination,
                'file_human_review_status' : i.human_review_status.state.name,
                'file_human_review_operation_id' : i.human_review_status.human_review_operation.split('/')[-1]
            })
        return info_array




def file_copy(array_having_file_names, bucket_name_with_folder):
        print("file_copy")
        for i in array_having_file_names:
            bucket_name = i.split('/')[-2]
            blob_name = i.split('/')[-1]
            destination_bucket_name = bucket_name_with_folder.split('/')[2]
            temp = bucket_name_with_folder.split('/')[3:]
            destination_blob_name = '/'.join(temp) + blob_name
            print("-- copy_blob --> ", bucket_name, '|', blob_name, '|', destination_bucket_name, '|', destination_blob_name)
            copy_blob(bucket_name, blob_name, destination_bucket_name, destination_blob_name)

def concurrentProcessing(batch_caller,daira_output_test,batch_array):
    print("--concurrentProcessing--")
    with concurrent.futures.ThreadPoolExecutor(max_workers = 3) as executor:
        future_to_url = {executor.submit(batch_caller, i, str('gs://'+daira_output_test)): i for i in batch_array}
    #for i in batch_array:
    #    print(i)
    #    batch_caller(i,str('gs://'+daira_output_test) )
    #    print("+++++ ", i, "  COMPLETED")
    print("*** processing completed ***")
    

def hello_world(request):
    print("--STARTED--")

    # delete previous ran diara-logs in firestore - if u r testing for same files
    try:
        previously_done_files = list(db_print()['filename'])
        print("previously_done_files : ", previously_done_files)
    except:
        previously_done_files = []


    input_bucket_files_list = bucket_lister(input_bucket_name)

    # pop the element (config file) from the input bucket file
    input_bucket_files_list.remove('gs://'+input_bucket_name+'/config/config.txt')

    files_to_process = [i for i in input_bucket_files_list if i.split('/')[-1] not in previously_done_files]
    print("files_to_process : ",files_to_process)
    start = 0
    end   = len(files_to_process)
    step  = 50


    process_batch_array = []
    for i in range(start, end, step):
        x = i
        process_batch_array.append(files_to_process[x:x+step])
    print("process_batch_array : ", process_batch_array)


    #dtstamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    #print("Date-Time-stamp : ", dtstamp)
    #diara_processing_test = str("daira-processing-test_"+dtstamp)
    #daira_output_test = str("daira-output-test_"+dtstamp)
    #print(diara_processing_test)
    #print(daira_output_test)


    #test vars
    diara_processing_test = 'daira-processing-test02'
    daira_output_test = 'daira-output-test02'


    try:
        print("creating : daira-processing-test")
        create_bucket_class_location(diara_processing_test) #  'daira-processing-test03'
        print("creating : daira-output-test")
        create_bucket_class_location(daira_output_test) # 'daira-output-test03'
    except Exception as exc:
        print("Bucket exists!")
        print(exc)


    bucket_cleaner(diara_processing_test) #'daira-processing-test03'
    lenght = len(process_batch_array)
    print(process_batch_array)


    for i in range(0, len(process_batch_array)):
        array_having_file_names = process_batch_array[i]
        bucket_name_with_folder = 'gs://'+ diara_processing_test +'/batches/'+str(i)+'/'
        print(i, ' | ', process_batch_array[i], ' | ', bucket_name_with_folder)
        file_copy(array_having_file_names, bucket_name_with_folder)


    batch_array = ['gs://'+ diara_processing_test +'/batches/'+str(i)+'/' for i in range(lenght)]
    print(batch_array)

    concurrentProcessing(batch_caller,daira_output_test,batch_array)

    print("metadata_array:")
    print(metadata_array)

    info_list_holder = [metadata_reader(i) for i in metadata_array]
    db_insert(info_list_holder)
    print(info_list_holder)
    print("--ENDED--")
    return 'Diara Done!'

