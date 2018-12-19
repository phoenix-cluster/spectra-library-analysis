""" analysis_pipeline.py

This tool search a project against the clusterd spectra to get Confident PSMs and new PSMs

Usage:
  analysis_pipeline.py --project=<project_id>  --minsize=<minClusterSize> [--silent_op=<y|n>]
  analysis_pipeline.py (--help | --version )

Options:
  -p, --project=<project_id>       project_id to be processed.
  -s, --minsize=<minClusterSize>   minimum cluster size to be matched.
  -t, --silent_op=<y|n>            run in silent mode, with default option y|n, use yes for all
  -h, --help                       Print this help message.
  -v, --version                    Print the current version.

"""

import sys
import os
from docopt import docopt
import urllib.request
import json
import time
import logging
import configparser
file_dir = os.path.dirname(__file__)
sys.path.append(file_dir)
#import phoenix_storage_access as phoenix
import mysql_storage_access as mysql_acc
from subprocess import Popen,PIPE,STDOUT

#max number of parallel jobs
parallel_jobs = 20

#resultFile name with running status
result_file_name = "resultFiles.txt.started"

config = configparser.ConfigParser()
config.read("%s/config.ini"%(file_dir))

def get_result_files(project_id):
    # xmlfiles = glob.glob(project_id+ '/*.xml')
    result_file_path = project_id + "/" + result_file_name
    result_files = list()
    try:
        with open (result_file_path, 'r') as f:
            for filename in f.readlines():
                result_files.append(filename.strip())
    except IOError:
        if project_id.startswith("E"):
            logging.info('resultFiles.txt does not exist for Enhancer Project %s! \nAbort pipeline.'%(project_id))
            print('resultFiles.txt does not exist for Enhancer Project %s! \nAbort pipeline.'%(project_id))
            sys.exit(0)

        logging.info('resultFiles.txt does not exist! Going to download data from PRIDE WebService')
        print('resultFiles.txt does not exist! Going to download data from PRIDE WebService')
        project_files_url = config.get("Urls","project_files_url")  + project_id
        try:
            with urllib.request.urlopen(project_files_url) as response:
                resp_str = response.read().decode('utf-8')
                json_obj = json.loads(resp_str)
                files = json_obj.get("list")

                for file in files:
                    if file["fileType"] == "RESULT":
                        result_files.append(file["fileName"])

                with open (result_file_path, 'w') as f:
                    for result_file in result_files:
                        f.write(result_file + "\n")
                    logging.info("Done of write result files to: " + result_file_path)
        except Exception as err:
            print(err)
            print("Failed to download result files from PRIDE WebService!")

    return result_files

def get_ms_run_names(result_files):
    ms_run_names = []
    for file in result_files:
        if file.lower().endswith(".xml.gz"):
            ms_run_names.append(file[:-7])
        elif file.lower().endswith(".xml"):
            ms_run_names.append(file[:-4])
        else:
            raise Exception("Filename: %s in resultFile does not end with .xml or .xml.gz" % (file))
    return (ms_run_names)

def create_unzip_shell_files(project_id, result_files):
    if len(result_files) < 1:
        return
    unzip_file = project_id + "/unzip.sh"
    cd_shell_path = "cd $(dirname $([ -L $0 ] && readlink -f $0 || echo $0))\n"
    temp_index = parallel_jobs
    with open(unzip_file,"w") as f:
        f.write(cd_shell_path)
        for file in result_files:
            file_path = project_id  + "/" + file
            if os.path.isfile(file_path) and file.endswith(".gz"):
                temp_index -= 1
                if temp_index == 0:
                    temp_index = parallel_jobs
                    f.write("gzip -d \"" + file + "\" ;\n")
                else:
                    f.write("gzip -d \"" + file + "\" &\n")

            elif os.path.isfile(project_id  + "/" + file[:-3]):
                continue #this file has been unzipped
            elif os.path.isfile(project_id  + "/" + file)and file.endswith(".xml"):
                continue #the uploaded file is unzipped
            else:
                print("----\n" + file + " is wrong in unzip step\n----\n")
                sys.exit()
                # raise Exception("result file %s is missing" % (file))

        print("done with creating unzip.sh")

def create_merge_shell_files(project_id, ms_run_names, type):
    if len(ms_run_names) < 1:
        logging.error("ms_run_names is empty")
        return

    import_file = project_id + "/merge_%s_csv.sh"%type

    cd_shell_path = "cd $(dirname $([ -L $0 ] && readlink -f $0 || echo $0))\n"
    output_file = "%s_%s.csv"%(project_id, type)
    command_str = "cat *_%s.csv > %s"%(type, output_file)

    with open(import_file,"w") as f:
        f.write(cd_shell_path)
        f.write("rm %s_%s.csv \n" % (project_id, type))
        f.write("rm %s_%s.csv \n" % (project_id, type))
        f.write(command_str)

    print("done with creating merge.sh")
    logging.info("done with creating merge.sh")

def create_convert_pridexml_to_csv_shell_files(project_id, ms_run_names):
    if len(ms_run_names) < 1:
        return

    shell_file = project_id + "/convert_pridexml_to_csv.sh"

    cd_shell_path = "cd $(dirname $([ -L $0 ] && readlink -f $0 || echo $0))\n"
    converter= config.get("PipeLine", "pride_xml_converter")

    command_str = "java -jar %s " + \
                   " -m -csv -p %s -i \"%s\" %s\n" #no importing to db here
#                   " -m -csv -ph -p %s -i \"%s\" %s\n"

    with open(shell_file,"w") as f:
        f.write(cd_shell_path)
        f.write("rm %s_psm.csv \n" % (project_id))
        f.write("rm %s_spec.csv \n" % (project_id))
        temp_n_parallel_jobs = int(parallel_jobs/2)
        temp_index = temp_n_parallel_jobs
        for ms_run_name in ms_run_names:
            file_name = ("%s.xml" % (ms_run_name))
            temp_index -= 1
            if temp_index == 0:
                temp_index = temp_n_parallel_jobs
                f.write(command_str % (converter, project_id, file_name, ';'))
            else:
                f.write(command_str % (converter, project_id, file_name, '&'))

        print("done with creating import_to_db.sh")

def create_convert_shell_files(project_id, ms_run_names):
    if len(ms_run_names) < 1:
        return
    convert_file = project_id + "/msconvert.sh"
    cd_shell_path = "cd $(dirname $([ -L $0 ] && readlink -f $0 || echo $0))\n"
    with open(convert_file,"w") as f:
        f.write(cd_shell_path)
        temp_index = parallel_jobs
        for ms_run_name in ms_run_names:
            file_name = ("%s.mgf" % (ms_run_name))
            temp_index -= 1
            if temp_index == 0:
                temp_index = parallel_jobs
                f.write("%s \"%s\" --mzML -o %s ;\n" % (config.get("PipeLine","msconvert"), file_name, "./"))
            else:
                f.write("%s \"%s\" --mzML -o %s &\n" % (config.get("PipeLine","msconvert"),file_name, "./"))
        print("Done with creating msconvert.sh")

def create_spectrast_shell_files(project_id, ms_run_names):
    if len(ms_run_names) < 1:
        return
    spectrast_search_file = project_id + "/spectrast_search.sh"
    cd_shell_path = "cd $(dirname $([ -L $0 ] && readlink -f $0 || echo $0))\n"
    with open(spectrast_search_file,"w") as f:
        f.write(cd_shell_path)
        temp_index = parallel_jobs
        spectrast = config.get("PipeLine","spectrast")
        speclib_file = config.get("PipeLine","speclib_file")
        for ms_run_name in ms_run_names:
            file_name = "%s.mzML" % (ms_run_name)
            temp_index -= 1
            if temp_index == 0:
                temp_index = parallel_jobs
                f.write("%s -sL %s\
                    \"%s\" ;\n" %(spectrast, speclib_file, file_name))
            else:
                f.write("%s -sL %s\
                    \"%s\" &\n" %(spectrast, speclib_file, file_name))
        print("done with creating spectrast_search.sh")

def main():
    arguments = docopt(__doc__, version='analysis_pipeline.py 1.0 BETA')
    project_id = arguments['--project'] or arguments['-p']
    min_cluster_size = arguments['--minsize'] or arguments['-s']
    min_cluster_size = int(min_cluster_size)
    is_silent = False
    if arguments.get('--silent_op', False) or arguments.get('-t', False):
        is_silent = True
        silent_op = arguments['--silent_op'] or arguments['-t']
    logging.basicConfig(filename="%s.log"%project_id, level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    logging.info("Start to analysis (pipeline) project: " + project_id)

    result_files = get_result_files(project_id)
    logging.info("Get %d files from resultFiles.txt for project %s: " %(len(result_files), project_id))
    logging.info(result_files)

    ms_run_names = get_ms_run_names(result_files)
    logging.info("Get %d msrun from resultFiles.txt for project %s: " %(len(ms_run_names), project_id))
    logging.info(ms_run_names)

    print(project_id)
    if not project_id.startswith("P"):
        # phoenix.upsert_analysis_status(project_id, 'started', 'localhost')
        mysql_acc.upsert_analysis_status(project_id, 'started')

    unzip_file = project_id + "/unzip.sh"
    redo = ''
    if is_silent:
        redo = silent_op
    if os.path.isfile(unzip_file):
        while redo != 'y' and redo != 'n':
            redo = input('the unzip.sh is already there, do you really want to redo the unzip process? y/n')
    if redo == 'y' or redo == '':
        create_unzip_shell_files(project_id, result_files)
        start = time.time()
        print("==--Starting unzip--==:\n")
        logging.info("==--Starting unzip--==:\n")
        output = os.popen('sh '+ project_id + "/unzip.sh").readlines()
        end = time.time()
        print(''.join(output) + "\n")
        logging.info(''.join(output) + "\n")
        logging.info("unziping take time %d seconds"%(end - start))


    convert_to_csv_shell = project_id + "/convert_pridexml_to_csv.sh"
    redo = ''
    if is_silent:
        redo = silent_op
    if os.path.isfile(convert_to_csv_shell):
        while redo != 'y' and redo != 'n':
            redo = input('the convert_pridexml_to_csv.sh is already there, do you really want to redo the convert to csv process? y/n')
    if redo == 'y' or redo == '':
        create_convert_pridexml_to_csv_shell_files(project_id, ms_run_names)
        start = time.time()
        print("==--Starting convert spectra & psm files --==:\n")
        logging.info("==--Starting convert spectra & psm files --==:\n")
        output1 = os.popen('sh '+ project_id + "/convert_pridexml_to_csv.sh").readlines()
        end = time.time()
        logging.info("convert to spectra/psm csv take time %d seconds"%(end - start))
        """
        create_merge_shell_files(project_id, ms_run_names, 'psm')
        create_merge_shell_files(project_id, ms_run_names, 'spec')
        print("==--Starting merge psm--==:\n" )
        logging.info("==--Starting merge psm--==:\n")
        output2 = os.popen('sh '+ project_id + "/merge_psm_csv.sh").readlines()
        print(''.join(output2) + "\n")
        logging.info(''.join(output2) + "\n")

        print("==--Starting merge spec--==:\n")
        logging.info("==--Starting merge spec--==:\n")
        output3 = os.popen('sh '+ project_id + "/merge_spec_csv.sh").readlines()
        print( ''.join(output3) + "\n")
        logging.info(''.join(output3) + "\n")
        """

    convert_to_mzml_file = project_id + "/msconvert.sh"
    redo = ''
    if is_silent:
        redo = silent_op
    if os.path.isfile(convert_to_mzml_file):
        while redo != 'y' and redo != 'n':
            redo = input('the msconvert.sh is already there, do you really want to redo the msconvert process? y/n')
    if redo == 'y' or redo == '':
        create_convert_shell_files(project_id, ms_run_names)
        start = time.time()
        logging.info("==--Starting msconvert--==:\n" )
        output = os.popen('sh '+ project_id + "/msconvert.sh").readlines()
        end = time.time()
        print( ''.join(output) + "\n")
        logging.info(''.join(output) + "\n")
        logging.info("msconvert take time %d seconds"%(end - start))


    spectrast_search_file = project_id + "/spectrast_search.sh"
    redo = ''
    if is_silent:
        redo = silent_op
    if os.path.isfile(spectrast_search_file):
        while redo != 'y' and redo != 'n':
            redo = input('the spectrast_search.sh is already there, do you really want to redo the spectrast search process? y/n')
    if redo == 'y' or redo == '':
        create_spectrast_shell_files(project_id, ms_run_names)
        start = time.time()
        print("==--Starting start spectrast search--==:\n")
        logging.info("==--Starting spectrast search--==:\n")
        output = os.popen('sh '+ project_id + "/spectrast_search.sh").readlines()
        end = time.time()
        print(''.join(output) + "\n")
        logging.info(''.join(output) + "\n")
        logging.info("spectrast searching take time %d seconds"%(end - start))
    #
    print("==--Starting enhancer analyze --==:\n")
    logging.info("==--Starting enhancer analyze --==:\n")
    start = time.time()
    file_dir = os.path.dirname(__file__)
    out = Popen(["python3", "%s/enhancer_analyze.py"%(file_dir), "-p", str(project_id), "-s", str(min_cluster_size)],  stdout=PIPE, stderr=STDOUT)
    end = time.time()
    stdoutput = str(out.communicate()[0])
    stdoutput = stdoutput.replace('\\n', "\n")
    return_code = out.returncode
    print( stdoutput )
    logging.info(stdoutput)
    logging.info("enhancer analyzing take time %d seconds"%(end - start))

    if return_code == 0:
        #phoenix.upsert_analysis_status(project_id, 'finished', 'localhost')
        mysql_acc.upsert_analysis_status(project_id, 'finished')
        os.rename(project_id + "/" + result_file_name, project_id + "/" + result_file_name[:-8])
    else:
        logging.info("This analysis %s is wrong"%project_id)
        #phoenix.upsert_analysis_status(project_id, 'finished_with_error', 'localhost')
        mysql_acc.upsert_analysis_status(project_id, 'finished_with_error')
if __name__ == "__main__":
    main()
