#!/usr/bin/python3
import json
import requests
from url_normalize import url_normalize
import logging
import sys
import argparse
import os
import xml.etree.ElementTree as ET
from mapping_xml_to_openehr import mapping_xml_openehr as mxo
from dictactfile import dictact

hostname='localhost'
port='8080'
templatename='crc_cohort7'
EHR_SERVER_BASE_URL = 'http://'+hostname+':'+port+'/ehrbase/rest/openehr/v1/'
EHR_SERVER_BASE_URL_FLAT = 'http://'+hostname+':'+port+'/ehrbase/rest/ecis/v1/composition/'

def get_compids(client,auth):
    '''Get pseudo:[ehrid,cid] dictionary for all the compositions in the EHRBase server'''
    myurl=url_normalize(EHR_SERVER_BASE_URL  + 'query/aql')
    data={}
    aqltext='''
    select e/ehr_id/value as EHR_id,
      c/uid/value as composition_id,
      c/context/other_context[at0001]/items[openEHR-EHR-CLUSTER.case_identification.v0]
      from ehr e contains composition c['openEHR-EHR-COMPOSITION.report.v1']
      '''
    data['q']=aqltext
    logging.info('Looking for compositions.....')
    print('Looking for compositions.....')
    response = client.post(myurl,headers={'Authorization':auth,'Content-Type': 'application/json'}, \
                data=json.dumps(data) )
    logging.info('done')
    print('done')
    dictact={}
    if(response.status_code<210 and response.status_code>199):
        results=json.loads(response.text)['rows']
        logging.info(f'found {len(results)} compositions')
        print(f'found {len(results)} compositions')
        for r in results:
            ehrid=r[0]
            cid=r[1]
            pseudo=r[2][0]['items'][0]['value']['value']
            dictact[pseudo]=[ehrid,cid]
    else:
        dictact['status']=str(response.status_code)
        dictact['headers']=str(response.headers)
    return dictact

def get_composition(client,auth,ehrid,cid):
    myurlu=url_normalize(EHR_SERVER_BASE_URL_FLAT+cid) 
    response = client.get(myurlu, \
        params={'ehrId':str(ehrid),'templateId':templatename,'format':'FLAT'}, \
        headers={'Authorization':auth,'Content-Type':'application/json'}, \
                )
    if(response.status_code <210 and response.status_code>199):
        compflat=json.loads(response.text)["composition"]
        return compflat
    else:           
        logging.warning(f"Couldn't retrieve the composition. Error{response.status_code}")
        logging.info(f"Couldn't retrieve the composition. Error{response.status_code}")
        logging.info(f'response.headers {response.headers}')
        logging.info(f'response.text {response.text}')   
        error={}
        error['status']=str(response.status_code)
        error['headers']=str(response.headers)     
        return error

def read_xml(file):
        '''return a list of trees, one tree for each BHPatient'''
        mytree = ET.parse(file)
        myroot = mytree.getroot()
        listoftrees=[]
        ns=''
        nop=0
        for ch in myroot:
                if (ch.tag.find('BHPatient') != -1):
                        nop+=1
#                       print('found')
#                       print(ch.tag)
                        listoftrees.append(ch)
        logging.info(f"Found {nop} patients in file {file}")
        print(f"Found {nop} patients in file {file}")
        return listoftrees

def find_ns(bhtree):
        '''find the namespace from a bhtree'''
        ns=''
        try:
                i=bhtree.tag.index('BHPatient')
                ns=bhtree.tag[0:i]
                print(f"namespace={ns}")
        except ValueError:
                print('namespace not found')    
        return ns

def getlen(xmltree):
    i=0
    for elem in xmltree.iter():
        i+=1
    return i


def main():
    global dictact
    parser = argparse.ArgumentParser()
    parser.add_argument('--loglevel',help='the logging level:DEBUG,INFO,WARNING,ERROR or CRITICAL',default='DEBUG')
    parser.add_argument('--inputdir',help='dir containing the xmls',default='/usr/local/data/WORK/OPENEHR/ECOSYSTEM/TO_AND_FROM_CONVERTER/CODE/FROM_DB_CSV_TO_XML_CONVERTER')
    parser.add_argument('--basename',help='basename to filter xml',default='patientsFromDb_')
    parser.add_argument('--templatename',help='template to use when posting',default='crc_cohort')
    parser.add_argument('--check',action='store_true', help='check the missing leafs for leafs that should be there but are not')
    args=parser.parse_args()

    #input
    loglevel=getattr(logging, args.loglevel.upper(),logging.WARNING)
    if not isinstance(loglevel, int):
            raise ValueError('Invalid log level: %s' % loglevel)
    logging.basicConfig(filename='./Check.log',filemode='w',level=loglevel)


    inputdir=args.inputdir
    print(f'inputdir given: {inputdir}')
    logging.info(f'inputdir given: {inputdir}')

    if not os.path.exists(inputdir):
        print(f'directory {inputdir} does not exist')
        logging.error(f'directory {inputdir} does not exist')
        sys.exit(1)

    basename=args.basename

    logging.info(f'basename given: {basename}')
    print(f'basename given: {basename}')
    #get the list of files
    filelist=[]
    for file in os.listdir(inputdir):
        if file.startswith(basename) and file.endswith(".xml"):
            logging.debug(f'file added {os.path.join(inputdir, file)}')
            filelist.append(file)
    #Now sort the list
    filelist.sort(key=lambda a: int(a.split('_')[1].split('.xml')[0]))
    for i,f in enumerate(filelist):
        logging.info(f'file {i+1} = {f}')

    filelistfullpath=[inputdir+'/'+f for f in filelist]

    # #mapping xml tag -> openEHR path in mxo

    # #read mapping terminology
    # mappingterminology=read_mapping_terminology()

    #init ehrbase
    client = requests.Session()
    client.auth = ('ehrbase-user','SuperSecretPassword')
    auth="Basic ZWhyYmFzZS11c2VyOlN1cGVyU2VjcmV0UGFzc3dvcmQ="

    # #find pseudo:[ehrid,cid]
    #get_compids time consuming. only first time done
    # 
    if dictact=={}:
        dictact=get_compids(client,auth)
        with open('dictactfile.py','w') as f:
            f.write('dicact={')
            for k in dictact.keys():
                f.write('"'+k+'" : ["'+dictact[k][0]+'" , "'+dictact[k][1]+'" ],')
            f.write('}')
    # logging.info('------dictact-------')
    # logging.info(dictact)

    #cycle over the xml files
    k=0
    for file in filelistfullpath:
        logging.debug('---------------------')
        logging.info(f'Processing {file}')
        print(f'Processing {file}')
        xmlpatients=read_xml(file)
        ns=find_ns(xmlpatients[0])

        if k==1:
            break
        k=k+1

        j=0
        for xmlpatient in xmlpatients:
            j=j+1
            basic_data=False
            hi=False
            sa=False
            su=False
            ph=False
            re=False
            ta=False
            ra=False
            BasicData=[]
            Histopathology=[]
            Sample=[]
            Surgery=[]
            Pharmacotherapy=[]
            Responsetotherapy=[]
            TargetedTherapy=[]
            Radiationtherapy=[]
            datalen=getlen(xmlpatient)
            print(f'datalen={datalen}')
            i=0
            for elem in xmlpatient.iter():
                i=i+1
                #tag identifier text=patient_number
                tag=elem.tag.split(ns)[1]
                text=elem.text
                attr=elem.attrib
                logging.debug(f'ns={ns} tag={str(tag)} text={str(text)} attr={str(attr)}')
                eventparse=False
                if hi: #histopathology event
                    if tag.startswith('Dataelement'):
                        histo[tag]=text
                        if i==datalen:
                            hi=False
                            Histopathology.append(histo)                    
                    elif tag=='Event':
                        hi=False
                        eventparse=True
                        Histopathology.append(histo)
                    elif i==datalen:
                        hi=False
                        Histopathology.append(histo)
                        logging.debug(f'histo={histo} Histo={Histopathology}')
                elif sa:#sample event
                    if tag.startswith('Dataelement'):
                        sample[tag]=text
                        if i==datalen:
                            sa=False
                            Sample.append(sample)                          
                    elif tag=='Event':
                        sa=False
                        eventparse=True
                        Sample.append(sample)
                    elif i==datalen:
                        sa=False
                        Sample.append(sample)                        
                elif su:#surgery event
                    if tag.startswith('Dataelement'):
                        surgery[tag]=text
                        if i==datalen:
                            su=False
                            Surgery.append(surgery)                          
                    elif tag=='Event':
                        su=False
                        eventparse=True
                        Surgery.append(surgery)
                    elif i==datalen:
                        su=False
                        Surgery.append(surgery)                        
                elif ph:#pharmacotherapy event
                    if tag.startswith('Dataelement'):                        
                        pharma[tag]=text
                        if i==datalen:
                            ph=False
                            Pharmacotherapy.append(pharma)                         
                    elif tag=='Event':
                        ph=False
                        eventparse=True
                        Pharmacotherapy.append(pharma)
                    elif i==datalen:
                        ph=False
                        Pharmacotherapy.append(pharma)                           
                elif re:#response to therapy event
                    if tag.startswith('Dataelement'):
                        rethe[tag]=text
                        if i==datalen:
                            re=False
                            Responsetotherapy.append(rethe)                         
                    elif tag=='Event':
                        re=False
                        eventparse=True
                        Responsetotherapy.append(rethe)
                    elif i==datalen:
                        re=False
                        Responsetotherapy.append(rethe)                           
                elif ta:#targeted therapy event
                    if tag.startswith('Dataelement'):
                        tathe[tag]=text
                        if i==datalen:
                            ta=False
                            TargetedTherapy.append(tathe)                          
                    elif tag=='Event':
                        ta=False
                        eventparse=True
                        TargetedTherapy.append(tathe)
                    elif i==datalen:
                        ta=False
                        TargetedTherapy.append(tathe)                          
                elif ra:#radiation therapy event
                    if tag.startswith('Dataelement'):
                        radthe[tag]=text
                        if i==datalen:
                            ra=False
                            Radiationtherapy.append(radthe)                                     
                    elif tag=='Event':
                        ra=False
                        eventparse=True
                        Radiationtherapy.append(radthe)
                    elif i==datalen:
                        ra=False
                        Radiationtherapy.append(radthe)                                
                elif basic_data: 
                    if tag.startswith('Dataelement'):
                        bada[tag]=text
                        if i==datalen:
                            basic_data=False
                            BasicData.append(bada)                           
                    elif tag=='Events':
                        BasicData.append(bada)
                        basic_data=False
                else: #anything else
                    if tag=='Identifier':
                        patient=text
                    elif tag=='BasicData':
                        basic_data=True
                        bada={}
                    elif tag=='Event':
                        eventparse=True

                if eventparse: #event to be parsed
                    if attr['eventtype']=='Surgery':
                        su=True
                        surgery={}
                        surgery['date']=attr['name']
                    elif attr['eventtype']=='Sample':
                        sa=True
                        sample={}
                        sample['date']=attr['name']
                    elif attr['eventtype']=='Histopathology':
                        hi=True
                        histo={}
                        histo['date']=attr['name']
                    elif attr['eventtype']=='Pharmacotherapy':  
                        ph=True                      
                        pharma={}
                        pharma['date']=attr['name']
                    elif attr['eventtype']=='Radiation therapy':
                        ra=True
                        radthe={}
                        radthe['date']=attr['name']
                    elif attr['eventtype']=='Response to therapy':
                        re=True
                        rethe={}
                        rethe['date']=attr['name']
                    elif attr['eventtype']=='Targeted Therapy':
                        ta=True
                        tathe={}
                        tathe['date']=attr['name']
                    else:
                        logging.warning(f'event unknown {tag} {text} {attr} ')                    

            logging.debug(f'+++++++++Patient={patient}+++++++++++++++++++')
            logging.debug(f'BasicData={BasicData}')
            logging.debug(f'Histopathology={Histopathology}')
            logging.debug(f'Surgery={Surgery}')
            logging.debug(f'Sample={Sample}')
            logging.debug(f'Pharmacotherapy={Pharmacotherapy}')
            logging.debug(f'Responsetotherapy={Responsetotherapy}')
            logging.debug(f'TargetedTherapy={TargetedTherapy}')            
            logging.debug(f'Radiationtherapy={Radiationtherapy}') 

            #get composition
            ehrid=dictact[patient][0]
            cid=dictact[patient][1]
            composition=get_composition(client,auth,ehrid,cid)
            if 'status' in composition:
                logging.info(f'error retrieving composition for patient={patient}')
                sys.exit(1)
            logging.debug('COMPOSITION')
            logging.debug(composition)

            # logging.debug(f'type(composition)={type(composition)}')
            # logging.debug(f'type(mxo)={type(mxo)}')
            
            #BasicData
            if len(BasicData)==1:
                for b in BasicData[0].keys():
                    if b=='date':
                        continue
                    # logging.debug(f'type(b)={type(b)}')
                    logging.debug('YYYYYYYYYYYYYYYYYYYY')
                    logging.debug(f'mapping {b}=>{mxo[b]}')
                    if len(mxo[b])==1:
                        # logging.debug(f'mxo[b][0]={mxo[b][0]}')
                        # logging.debug(f'{composition["crc_cohort7/diagnostic_examinations/liver_imaging/liver_imaging"]}')
                        # logging.debug(f'{composition[mxo[b][0]]}')
                        logging.debug(f'BasicData {BasicData[0][b]}=>{composition[mxo[b][0]]}')    
                    else:
                        for l in range(len(mxo[b])):
                            logging.debug(f'BasicData {BasicData[0][b]}=>{composition[mxo[b][l]]}')
                    logging.debug('YYYYYYYYYYYYYYYYYYYY')        
            if len(Histopathology)==1:
                for h in Histopathology[0].keys():
                    if h=='date':
                        continue                
                    logging.debug('ZZZZZZZZZZZZZZZZZZZZ')                            
                    logging.debug(f'mapping {h}=>{mxo[h]}')
                    if len(mxo[h])==1:
                        logging.debug(f'Histopathology {Histopathology[0][h]}=>{composition[mxo[h][0]]}')
                    else:
                        for l in range(len(mxo[h])): 
                            logging.debug(f'Histopathology {Histopathology[0][h]}=>{composition[mxo[h][l]]}')            
                    logging.debug('ZZZZZZZZZZZZZZZZZZZZ')   
            else:
                pass

            if len(Sample)==1:
                for s in Sample[0].keys():
                    if s=='date':
                        continue
                    logging.debug('AAAAAAAAAAAAAAAAAAAA')        
                    logging.debug(f'mapping {s}=>{mxo[s]}')                    
                    if len(mxo[s])==1:
                        logging.debug(f'Sample {Sample[0][s]}=>{composition[mxo[s][0]]}')
                    else:
                        for l in range(len(mxo[s])): 
                            logging.debug(f'Sample {Sample[0][s]}=>{composition[mxo[s][l]]}')                    
                    logging.debug('AAAAAAAAAAAAAAAAAAAA')          
            else:
                pass

            if len(Surgery)==1:
                for s in Surgery[0].keys():
                    if s=='date':
                        continue        
                    logging.debug('BBBBBBBBBBBBBBBBBBBB') 
                    logging.debug(f'mapping {s}=>{mxo[s]}')
                    if len(mxo[s])==1:
                        logging.debug(f'Surgery {Surgery[0][s]}=>{composition[mxo[s][0]]}')
                    else:
                        for l in range(len(mxo[s])): 
                            logging.debug(f'Surgery {Surgery[0][s]}=>{composition[mxo[s][l]]}')                    
                    logging.debug('BBBBBBBBBBBBBBBBBBBB') 
            else:
                pass

            #make data comparison

                #print(f'i={i}')
            if j==2:
                break



if __name__ == '__main__':
    main()




