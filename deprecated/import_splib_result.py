""" import_splib_result.py

This tool get the target spectra and search hits from the spectra library. 
The library is built from the PRIDE Cluster consensus spectra without identified information to use.

Usage:
  import_splib_result.py --input=<results.pep.xml> [--tablename=<tablename>]
  import_splib_result.py (--help | --version)

Options:
  -i, --input=<results.pep.xml>        Path to the result .pep.xml file to process.
  --tablename=[tablename]             Table name in MySQL db to store the spectra library search result.
  --host=[host_name_of_db]             Host name or IP address of the MySQL server.
  -h, --help                           Print this help message.
  -v, --version                        Print the current version.

"""
import sys
import os
from docopt import docopt
import xml.etree.ElementTree as ET
import pymysql.cursors

def check_table(connection,table_name):
    """
    Check the table name exists or not,
    create it if not exists,
    ask user if they want to overwrite the table if exists.
    """
    table_exists = None
    create_new = None
    over_write_table = True

    tb_exists = "SHOW TABLES LIKE '" + table_name + "';"
    # create a table
    tb_create = "CREATE TABLE `" + table_name + "` ("                     + \
                    "id int(15) NOT NULL AUTO_INCREMENT,"    + \
                    "spec_title varchar(100) COLLATE utf8_bin NOT NULL,"    + \
                    "scan_in_lib int(15) COLLATE utf8_bin NOT NULL,"    + \
                    "dot float NOT NULL,"    + \
                    "delta float NOT NULL,"    + \
                    "dot_bias float NOT NULL,"    + \
                    "mz_diff float NOT NULL,"    + \
                    "fval float NOT NULL,"    + \
                    "PRIMARY KEY (id)" + ")ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_bin;"
    print(tb_create)
    """
    <search_score name="dot" value="0.493"/>                                       
    <search_score name="delta" value="0.103"/>                                     
    <search_score name="dot_bias" value="0.000"/>                                  
    <search_score name="precursor_mz_diff" value="0.452"/>                         
    <search_score name="hits_num" value="13480"/>                                  
    <search_score name="hits_mean" value="0.070"/>                                 
    <search_score name="hits_stdev" value="0.054"/>                                
    <search_score name="fval" value="0.379"/>                                      
    <search_score name="p_value" value="-1.000e+00"/>                              
    <search_score name="KS_score" value="0.000"/>                                  
    <search_score name="first_non_homolog" value="2"/>                             
    <search_score name="open_mod_mass" value="0.000"/>                             
    <search_score name="open_mod_locations" value=""/>                             
    <search_score name="charge" value="2"/>                                        
    <search_score name="lib_file_offset" value="823479617"/>                       
    <search_score name="lib_probability" value="1.0000"/>                          
    <search_score name="lib_status" value="Normal"/>                               
    <search_score name="lib_num_replicates" value="1"/>                            
    <search_score name="lib_remark" value="_NONE_"/>                               
    """

    try:
        with connection.cursor() as cursor:
            cursor.execute(tb_exists)
            result = cursor.fetchone()
            connection.commit()
            if result != None :
                table_exists = True
   #except IOError as e:
            else:
                print("Table does not exists")
                table_exists = False
                create_new = True
            
            if table_exists and not over_write_table: 
                print("The table" + table_name + "is already exists, do you really want to overwrite it?")
                answer = input("please input yes | no:  ")
                while(answer != 'yes' and answer != 'no'):
                    answer = input("please input yes | no:")
                if answer == 'no':
                    print("Going to exit.")
                    sys.exit(0)
                else:
                    create_new = True 

#            if over_write_table or create_new :
            if True:
                if table_exists:
                    print("Start droping the tables")
                    cursor.execute("DROP TABLE IF EXISTS `" + table_name + "`;")
                cursor.execute(tb_create)
                connection.commit()
    finally:
        print ("checked table")



def connect_and_check(mysql_host, table_name):
#build the connection
    connection = pymysql.connect(host=mysql_host,
                            user='pride_cluster_t',
                            password='pride123',
                            db='pride_cluster_t',
                            charset='utf8mb4',
                            cursorclass=pymysql.cursors.DictCursor)
    print("Opened database successfully");
    #deal with the table name
    check_table(connection, table_name)
    return connection



def get_lib_spec_index(protein_str):
    words = protein_str.split("_") 
    return words[2]

def remove_pepxml_ext(path_name):
    return path_name[:-7]

def get_spec_title(mzML_path):
    mzMLfile = open(mzML_path)
    ns_str = "{http://psi.hupo.org/ms/mzml}"
    tree = ET.parse(mzMLfile)
    root = tree.getroot()
    id_map = {}
    for spectrum in root.iter(ns_str + "spectrum"):
        index = spectrum.attrib.get('index')
        for cvParam in spectrum.iterfind(ns_str + 'cvParam'):
            name = cvParam.attrib.get('name')
            if name == 'spectrum title':
                id_value = cvParam.attrib.get('value')
                id_map[index] = id_value
                if id_value == None:
                    raise("Spectrum index" + index + " has empty spectrum title")
    mzMLfile.close()
    return(id_map)

def insert_to_db(connection, table_name, search_result_set):
    """    
    "spec_title varchar(100) NOT NULL,"    + \
    "scan_in_lib int(15) COLLATE utf8_bin NOT NULL,"    + \
    "dot float NOT NULL,"    + \
    "delta float NOT NULL,"    + \
    "dot_bias float NOT NULL,"    + \
    "mz_diff float NOT NULL,"    + \
    "fval float NOT NULL,"    + \
    """
    spec_title = list(search_result_set.keys())[0]
    search_result = search_result_set.get(spec_title)
    scan_in_lib = search_result.get('lib_spec_index')
    dot = search_result.get('dot')
    delta = search_result.get('delta')
    dot_bias = search_result.get('dot_bias')
    mz_diff = search_result.get('precursor_mz_diff')
    fval = search_result.get('fval')


    insert_db = "INSERT INTO `" + table_name +"`" +\
                "(spec_title, scan_in_lib, dot, delta, dot_bias, mz_diff, fval) VALUES " +\
                "('" + spec_title + "','" + scan_in_lib + "','" + dot + "','" + delta +"','" + dot_bias + "','" + mz_diff + "','" + fval + "')"
    with connection.cursor() as cursor:
        cursor.execute(insert_db)


def importafile(connection, table_name, pepxml_path, title_map):
    ns_str = "{http://regis-web.systemsbiology.net/pepXML}"
    tree = ET.parse(pepxml_path)
    root = tree.getroot()

    print("Starting to import " + pepxml_path)
    msms_run_summary = root[0]
    count = 0
    for spectrum_query in msms_run_summary.iterfind(ns_str + "spectrum_query"):
        #start_scan = spectrum_query.attrib.get('start_scan')
        #end_scan = spectrum_query.attrib.get('end_scan')
        #if start_scan != end_scan :
        #    raise Exception ("Some thing wrong with this spectrum_query, start_scan %d != end_scan %d"%(start_scan, end_scan))
        start_scan = spectrum_query.attrib.get('start_scan')
        scan_num_in_mzml = str(int(start_scan) - 1) #scan_num start at 1 in pep.xml, but at 0 in mzML
        spectrum = title_map.get(scan_num_in_mzml)
        if spectrum == None:
            raise Exception("Spectrum in pepxml at scan " + start_scan + " has no spectrum title")
        count = count + 1
        
        search_result = spectrum_query[0]
        if search_result.tag != ns_str + 'search_result':
            raise Exception ("Some thing wrong with this spectrum_query, search_result is not the first element, but %s"%search_result.tag)
        
        protein_str = "" 
        search_results = {}
        for search_hit in spectrum_query.iterfind(ns_str + "search_result/"+ ns_str + 'search_hit') :
            if int(search_hit.attrib.get('hit_rank')) > 1:
                raise Exception ("Some thing wrong with this spectrum_query, search_hit is more than one: %s"%spectrum_query.attrib.get('spectrum'))
            protein_str = search_hit.attrib.get("protein")
            lib_spec_index = get_lib_spec_index(protein_str)
            search_scores = {}
            search_scores['lib_spec_index'] = lib_spec_index
            for search_score in search_hit.getchildren():
                score_name = search_score.attrib.get('name')
                score_value = search_score.attrib.get('value')
                search_scores[score_name] = score_value 
        search_results[spectrum] = search_scores
        insert_to_db(connection, table_name, search_results)
    connection.commit()    
    print("Importing of " + pepxml_path + "is done.")
    print("Totally " + str(count) + "spectra have been imported.")

def main():
    arguments = docopt(__doc__, version='import_splib_result.py 1.0 BETA')
    input_path = arguments['--input'] or arguments['-i']
    
    table_name = "test_spec_lib_search_result_1"

    if arguments['--tablename']:
        table_name = arguments['--tablename']
    connection = connect_and_check('localhost', table_name)
   
#    index_title_map = get_index_map("../../spec_lib_searching/PXD000021/head.mzML")

    if os.path.isfile(input_path):
        mzML_path = remove_pepxml_ext(input_path) + "mzML"
        print(mzML_path)
        title_map = get_spec_title(mzML_path)
        importafile(connection, table_name, input_path, title_map)
    else:
    	for file in os.listdir(input_path):
            if not file.lower().endswith('.pep.xml'):
                continue
            mzML_path = remove_pepxml_ext(file) + "mzML"
            print(mzML_path)
            title_map = get_spec_title(mzML_path)
            importafile(connection, table_name, input_path + "/" + file, title_map)

if __name__ == "__main__":
    main()
