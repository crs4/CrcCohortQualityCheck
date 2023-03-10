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
import re
from mapping_values import vmapping_xml_openehr as vmap
import difflib
from multiplicity import multi

try:
    from dictactfile import dictact
except ModuleNotFoundError as err:
    dictact={}
    

pat=re.compile('\s*')


hostname='localhost'
port='8080'
templatenamedefault='BBMRI-ERIC_Colorectal_Cancer_Cohort_Report'
EHR_SERVER_BASE_URL = 'http://'+hostname+':'+port+'/ehrbase/rest/openehr/v1/'
EHR_SERVER_BASE_URL_FLAT = 'http://'+hostname+':'+port+'/ehrbase/rest/ecis/v1/composition/'

def get_composition_file(filename):
    with open(filename,'r') as f:
        composition = json.load(f)
        #logging.debug(f'composition retrieved: {composition}')
        logging.debug(f"composition {composition['bbmri-eric_colorectal_cancer_cohort_report/context/biobank/biobank_name']}")
        return composition


def get_compids_file(dircomp,basename):
    '''Get pseudo:composition_full_filename dictionary for all the compositions in the dir dircomp'''
    dictactfile={}
    for filex in os.listdir(dircomp):
        if filex.startswith(basename) and filex.endswith(".json"):
            patientnumber=filex.split('_')[3].split('.json')[0]
            fullpathfilename=os.path.join(dircomp, filex)
            dictactfile[patientnumber]=fullpathfilename
            logging.debug(f'file {fullpathfilename} added to dictactfile for patient {patientnumber}')
    return dictactfile            


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

def get_composition(client,auth,ehrid,cid,templatename):
    myurlu=url_normalize(EHR_SERVER_BASE_URL_FLAT+cid) 
    response = client.get(myurlu, \
        params={'ehrId':str(ehrid),'templateId':templatename,'format':'FLAT'}, \
        headers={'Authorization':auth,'Content-Type':'application/json'}, \
                )
    if(response.status_code <210 and response.status_code>199):
        response.encoding='utf-8'
        compflat=json.loads(response.text)["composition"]
        # for key in compflat:
        #     compflat[key]=compflat[key].encode('latin1').decode('utf8')
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

def read_xml(filex):
        '''return a list of trees, one tree for each BHPatient'''
        mytree = ET.parse(filex)
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
        logging.info(f"Found {nop} patients in file {filex}")
        print(f"Found {nop} patients in file")
        return listoftrees

def find_ns(bhtree):
        '''find the namespace from a bhtree'''
        ns=''
        try:
                i=bhtree.tag.index('BHPatient')
                ns=bhtree.tag[0:i]
                logging.debug(f"namespace={ns}")
        except ValueError:
                logging.warning('namespace not found')    
        return ns

def getlen(xmltree):
    i=0
    for elem in xmltree.iter():
        i+=1
    return i


def comparexml2comp(datatitle,xmlelement,composition,fd,Patient,notload):
    ndifff=0
    nalan=0
    if len(xmlelement)==1:
        for b in xmlelement[0].keys():
            if b=='date':
                continue
            # logging.debug(f'type(b)={type(b)}')
            logging.debug('YYYYYYYYYYYYYYYYYYYY')
            logging.debug(f'b={b}')
            logging.debug(f'datatitle={datatitle}')
            if b in vmap:
                logging.debug('b in vmap')
                valuexml=xmlelement[0][b]
                
                logging.debug(f'mxo[b]={mxo[b]}')
                logging.debug(f'vmap[b]={vmap[b]}')
                if valuexml==None or pat.fullmatch(valuexml) != None:
                    if mxo[b][0] in composition:
                        valuecomp=composition[mxo[b][0]]
                        logging.debug(f'valuexml={valuexml} valuecomp={valuecomp}')
                        if valuecomp=='None':
                            nalan+=1                       
                            logging.debug(f'mapping {b}=>{mxo[b]}')
                            logging.debug(f"{datatitle} xml={valuexml} realcomp={valuecomp}")
                            continue
                        else:
                            nalan+=1
                            ndifff+=1
                            logging.debug(f'1DIFFERENT! Patient={Patient}')
                            logging.debug(f'mapping {b}=>{mxo[b]}')
                            logging.debug(f"{datatitle} xml={valuexml} realcomp={valuecomp}")
                            logging.debug(f'empty valuexml')
                            fd.write(f'1DIFFERENT! Patient={Patient}')
                            fd.write(f'mapping {b}=>{mxo[b]}')
                            fd.write(f"{datatitle} xml={valuexml} realcomp={valuecomp}")
                            fd.write(f'empty valuexml')
                            continue           
                    else:
                        nalan+=1
                        logging.debug(f'mapping {b}=>{mxo[b]}')
                        logging.debug(f"{datatitle} xml={valuexml} realcomp=nothing")
                        logging.debug(f'empty valuexml mapped to NO element')
                        continue         
                if mxo[b][0] in composition:                 
                    valuecomp=composition[mxo[b][0]]
                    logging.debug(f'valuexml={valuexml} valuecomp={valuecomp}')
                    if len(mxo[b])==1:
                        if vmap[b][valuexml] == valuecomp:
                            nalan+=1
                            logging.debug(f'mapping {b}=>{mxo[b]}')
                            logging.debug(f"{datatitle} xml={valuexml} expectedcomp={vmap[b][valuexml]} realcomp={valuecomp}") 
                        else:
                            nalan+=1
                            ndifff+=1
                            logging.debug(f'2DIFFERENT! Patient={Patient}')
                            logging.debug(f'mapping {b}=>{mxo[b]}')
                            logging.debug(f"{datatitle} xml={valuexml} expectedcomp={vmap[b][valuexml]} realcomp={valuecomp}") 
                            fd.write(f'2DIFFERENT! Patient={Patient}')                        
                            fd.write(f'mapping {b}=>{mxo[b]}\n')
                            fd.write(f"{datatitle} xml={valuexml} expectedcomp={vmap[b][valuexml]} realcomp={valuecomp}\n")
                    else:
                        i=0
                        if mxo[b][1].endswith('|value'):
                            i=1
                        elif mxo[b][2].endswith('|value'):
                            i=2
                        valuexml=xmlelement[0][b]
                        valuecomp=composition[mxo[b][i]]
                        if vmap[b][valuexml] == valuecomp:
                            nalan+=1
                            logging.debug(f'mapping {b}=>{mxo[b]}')
                            logging.debug(f"{datatitle} xml={valuexml} expectedcomp={vmap[b][valuexml]} realcomp={valuecomp}") 
                        else:
                            nalan+=1
                            ndifff+=1
                            logging.debug(f'3DIFFERENT! Patient={Patient}')
                            logging.debug(f'mapping {b}=>{mxo[b]}')
                            logging.debug(f'{datatitle} {valuexml}=>{valuecomp}')  
                            fd.write(f'3DIFFERENT! Patient={Patient}')                       
                            fd.write(f'mapping {b}=>{mxo[b]}\n')
                            fd.write(f"xml={valuexml} expectedcomp={vmap[b][valuexml]} realcomp={valuecomp}\n")
                else:
                    nalan+=1
                    ndifff+=1
                    logging.debug(f'4DIFFERENT! Patient={Patient}')
                    logging.debug(f'mapping {b}=>{mxo[b]}')
                    logging.debug(f'{datatitle} {valuexml}=>NO ENTRY')  
                    fd.write(f'4DIFFERENT! Patient={Patient}')                       
                    fd.write(f'mapping {b}=>{mxo[b]}\n')
                    fd.write(f"xml={valuexml} expectedcomp={vmap[b][valuexml]} realcomp=NO ENTRY\n")
            else:
                logging.debug('b not in vmap SINGLE')
                valuexml=xmlelement[0][b]
                if valuexml==None or pat.fullmatch(valuexml) != None:
                    if mxo[b][0] in composition:
                        valuecomp=composition[mxo[b][0]]
                        logging.debug(f'valuexml={valuexml} valuecomp={valuecomp}')
                        if valuecomp=='None':
                            nalan+=1                       
                            logging.debug(f'mapping {b}=>{mxo[b]}')
                            logging.debug(f"{datatitle} xml={valuexml} realcomp={valuecomp}")
                            continue
                        else:
                            nalan+=1
                            ndifff+=1
                            logging.debug(f'5DIFFERENT! Patient={Patient}')
                            logging.debug(f'mapping {b}=>{mxo[b]}')
                            logging.debug(f'{datatitle} xml={valuexml}=>comp={valuecomp}')  
                            logging.debug(f'empty valuexml ')
                            fd.write(f'5DIFFERENT! Patient={Patient}')
                            fd.write(f'mapping {b}=>{mxo[b]}')
                            fd.write(f'{datatitle} xml={valuexml}=>comp={valuecomp}')  
                            fd.write(f'empty valuexml ')
                            continue  
                    else:
                        nalan+=1
                        logging.debug(f'mapping {b}=>{mxo[b]}')
                        logging.debug(f'{datatitle} {valuexml}=>nothing')  
                        logging.debug(f'empty valuexml mapped to NO element')
                        continue
                if mxo[b][0] in composition:
                    valuecomp=composition[mxo[b][0]]
                    logging.debug(f'valuexml={valuexml} valuecomp={valuecomp}')
                    if isinstance(valuecomp,bool):
                        valuecomp=str(valuecomp)
                    logging.debug(f'valuexml={valuexml} valuecomp={valuecomp}')
                    logging.debug(f'mxo[b]={mxo[b]}')
                    if valuexml==valuecomp:
                        nalan+=1
                        logging.debug(f'mapping {b}=>{mxo[b]}')
                        logging.debug(f"{datatitle} xml={valuexml} realcomp={valuecomp}")
                    else:
                        if  mxo[b][0].endswith('age_at_diagnosis'):
                            valuexml2='P'+valuexml+'Y'
                            if valuexml2==valuecomp:
                                nalan+=1
                                logging.debug(f'mapping {b}=>{mxo[b]}')
                                logging.debug(f"{datatitle} xml={valuexml} xml2={valuexml2} realcomp={valuecomp}")
                            else:
                                nalan+=1
                                ndifff+=1
                                logging.debug(f'6DIFFERENT! Patient={Patient}')
                                logging.debug(f'mapping {b}=>{mxo[b]}')
                                logging.debug(f'{datatitle} {valuexml}=>{valuecomp}')   
                                fd.write(f'6DIFFERENT! Patient={Patient}')                      
                                fd.write(f'mapping {b}=>{mxo[b]}\n')
                                fd.write(f"xml={valuexml}  xml2={valuexml2} realcomp={valuecomp}\n")  
                        elif mxo[b][0].endswith('overall_survival_status') or \
                            mxo[b][0].endswith('surgery_start_relative') or \
                            mxo[b][0].endswith('date_of_end_of_pharmacotherapy') or \
                            mxo[b][0].endswith('date_of_start_of_pharmacotherapy') or \
                            mxo[b][0].endswith('time_of_therapy_response') or \
                            mxo[b][0].endswith('date_of_start_of_targeted_therapy') or \
                            mxo[b][0].endswith('date_of_end_of_targeted_therapy') or \
                            mxo[b][0].endswith('date_of_start_of_radiation_therapy') or \
                            mxo[b][0].endswith('date_of_end_of_radiation_therapy') or \
                            mxo[b][0].endswith('time_of_recurrence'):
                            v1=int(valuexml)*7
                            if notload:
                                valuexml2='P'+valuexml+'W'
                            else:
                                valuexml2='P'+str(v1)+'D'
                            if valuexml2==valuecomp:
                                nalan+=1
                                logging.debug(f'mapping {b}=>{mxo[b]}')
                                logging.debug(f"{datatitle} xml={valuexml} xml2={valuexml2} realcomp={valuecomp}")
                            else:
                                nalan+=1
                                ndifff+=1
                                logging.debug(f'7DIFFERENT! Patient={Patient}')
                                logging.debug(f'mapping {b}=>{mxo[b]}')
                                logging.debug(f'{datatitle} {valuexml}=>{valuecomp}')    
                                fd.write(f'7DIFFERENT! Patient={Patient}')                     
                                fd.write(f'mapping {b}=>{mxo[b]}\n')
                                fd.write(f"xml={valuexml}  xml2={valuexml2} realcomp={valuecomp}\n")  
                        elif mxo[b][0].endswith('date_of_diagnosis') or \
                            mxo[b][0].endswith('year_of_sample_collection'):
                            l1=len(valuexml)
                            #make exception for patient 59939 that is expressed as 1995-10-4
                            if l1==9:
                                valuexml2=valuexml[:-1]+'0'+valuexml[-1]
                                valuexml=valuexml2
                                l1=len(valuexml)
                            valuecomp2=valuecomp[:l1]
                            if valuexml==valuecomp2:
                                nalan+=1
                                logging.debug(f'mapping {b}=>{mxo[b]}')
                                logging.debug(f"{datatitle} xml={valuexml} comp2={valuecomp2} realcomp={valuecomp}")
                            else:
                                nalan+=1
                                ndifff+=1
                                logging.debug(f'8DIFFERENT! Patient={Patient}')
                                logging.debug(f'mapping {b}=>{mxo[b]}')
                                logging.debug(f'{datatitle} {valuexml}=>{valuecomp}') 
                                fd.write(f'8DIFFERENT! Patient={Patient}')                        
                                fd.write(f'mapping {b}=>{mxo[b]}\n')
                                fd.write(f"xml={valuexml} comp2={valuecomp2} realcomp={valuecomp}\n")                              
                        else:
                            nalan+=1
                            ndifff+=1
                            logging.debug(f'9DIFFERENT! Patient={Patient}')
                            logging.debug(f'mapping {b}=>{mxo[b]}')
                            logging.debug(f'{datatitle} {valuexml}=>{valuecomp}')  
                            fd.write(f'9DIFFERENT! Patient={Patient}')                       
                            fd.write(f'mapping {b}=>{mxo[b]}\n')
                            fd.write(f"xml={valuexml} realcomp={valuecomp}\n")   
                else:
                    nalan+=1
                    ndifff+=1
                    logging.debug(f'10DIFFERENT! Patient={Patient}')
                    logging.debug(f'mapping {b}=>{mxo[b]}')
                    logging.debug(f'{datatitle} {valuexml}=>NO ENTRY')  
                    fd.write(f'10DIFFERENT! Patient={Patient}')                       
                    fd.write(f'mapping {b}=>{mxo[b]}\n')
                    fd.write(f"xml={valuexml} realcomp=NO ENTRY\n")                    
    else: #the macroelement is repeated more than once. Ex sample1 sample2
        for j in range(len(xmlelement)):
            logging.debug('LLLLLLLLLLL')
            logging.debug(j)
            logging.debug(xmlelement)
            multipath=multi[datatitle]
            newpath=multipath[:-1]+str(j)
            logging.debug(f'multipath={multipath} newpath={newpath}')
            for b in xmlelement[j].keys():
                if b=='date':
                    continue
                logging.debug('YYYYYYYYYYYYYYYYYYYY')
                logging.debug(f'b={b}')
                #print(b)
                #print(datatitle)                 
                # logging.debug(f'type(b)={type(b)}')
                if b in vmap:
                    valuexml=xmlelement[j][b]
                    logging.debug(f'valuexml={valuexml}')
                    if valuexml==None or pat.fullmatch(valuexml) != None:
                            jmult=zeromult.replace(multipath,newpath)
                            if jmult in composition:
                                valuecomp=composition[jmult]
                                logging.debug(f'valuexml={valuexml} valuecomp={valuecomp}')
                                if valuecomp=='None':
                                    nalan+=1                       
                                    logging.debug(f'mapping {b}=>{mxo[b]}')
                                    logging.debug(f"{datatitle} xml={valuexml} realcomp={valuecomp}")
                                    continue
                                else:
                                    nalan+=1
                                    ndifff+=1
                                    logging.debug(f'11DIFFERENT! Patient={Patient}')
                                    logging.debug(f'mapping {b}=>{mxo[b]}')
                                    logging.debug(f'{datatitle} {valuexml}=>{valuecomp}')  
                                    logging.debug(f'empty valuexml ')
                                    fd.write(f'11DIFFERENT! Patient={Patient}')
                                    fd.write(f'mapping {b}=>{mxo[b]}')
                                    fd.write(f'{datatitle} {valuexml}=>{valuecomp}')  
                                    fd.write(f'empty valuexml ')
                                    continue  
                            else:
                                nalan+=1
                                logging.debug(f'mapping {b}=>{mxo[b]}')
                                logging.debug(f'{datatitle} {valuexml}=>nothing')  
                                logging.debug(f'empty valuexml mapped to NO element')
                                continue     

                    if len(mxo[b])==1:
                        zeromult=mxo[b][0]
                        jmult=zeromult.replace(multipath,newpath)
                        if jmult in composition:
                            valuecomp=composition[jmult]
                            logging.debug(f'valuecomp={valuecomp}')
                            v1=vmap[b][valuexml] 
                            v2=valuecomp
                            if v1 == v2:
                                nalan+=1
                                logging.debug(f'mapping {b}=>{mxo[b]} j={j} jmult={jmult}')
                                logging.debug(f"{datatitle} xml={valuexml} expectedcomp={v1} realcomp={valuecomp}")            
                            else:
                                nalan+=1
                                ndifff+=1
                                logging.debug(f'12DIFFERENT! Patient={Patient}')
                                logging.debug(f'mapping {b}=>{mxo[b]} j={j} jmult={jmult}')
                                logging.debug(f"{datatitle} xml={valuexml} expectedcomp={v1} realcomp={valuecomp}")  
                                fd.write(f'12DIFFERENT! Patient={Patient}')                       
                                fd.write('mapping {b}=>{mxo[b]} j={j} jmult={jmult}\n')
                                fd.write(f"{datatitle} xml={valuexml} expectedcomp={v1} realcomp={valuecomp}\n")
                        else:
                            nalan+=1
                            ndifff+=1
                            logging.debug(f'13DIFFERENT! Patient={Patient}')
                            logging.debug(f'mapping {b}=>{mxo[b]} j={j} jmult={jmult}')
                            logging.debug(f"{datatitle} xml={valuexml} expectedcomp={vmap[b][valuexml]} realcomp=MISSING ENTRY") 
                            fd.write(f'13DIFFERENT! Patient={Patient}')                        
                            fd.write('mapping {b}=>{mxo[b]} j={j} jmult={jmult}\n')
                            fd.write(f"{datatitle} xml={valuexml} expectedcomp={vmap[b][valuexml] } realcomp=MISSING ENTRY\n")                           
                    else:
                        i=0
                        if mxo[b][1].endswith('|value'):
                            i=1
                        elif mxo[b][2].endswith('|value'):
                            i=2
                        #print(valuexml)
                        #print(b)
                        #print(mxo[b][i])
                        zeromult=mxo[b][i]
                        jmult=zeromult.replace(multipath,newpath)
                        if jmult in composition:
                            valuecomp=composition[jmult]
                            logging.debug(f'valuecomp={valuecomp}')
                            v1=vmap[b][valuexml] 
                            v2=valuecomp
                            if v1 == v2:
                                nalan+=1             
                                logging.debug(f'mapping {b}=>{mxo[b]} j={j} jmult={jmult}')
                                logging.debug(f"{datatitle} xml={valuexml} expectedcomp={v1} realcomp={valuecomp}")            
                            else:
                                nalan+=1
                                ndifff+=1
                                logging.debug(f'14DIFFERENT! Patient={Patient}')
                                logging.debug(f'mapping {b}=>{mxo[b]} j={j} jmult={jmult}')
                                logging.debug(f"{datatitle} xml={valuexml} expectedcomp={vmap[b][valuexml]} realcomp={valuecomp}")  
                                fd.write(f'14DIFFERENT! Patient={Patient}')                      
                                fd.write('mapping {b}=>{mxo[b]} j={j} jmult={jmult}\n')
                                fd.write(f"{datatitle} xml={valuexml} expectedcomp={v1} realcomp={valuecomp}\n") 
                        else:
                            nalan+=1
                            ndifff+=1
                            logging.debug(f'15DIFFERENT! Patient={Patient}')
                            logging.debug(f'mapping {b}=>{mxo[b]} j={j} jmult={jmult}')
                            logging.debug(f"{datatitle} xml={valuexml} expectedcomp={vmap[b][valuexml]} realcomp=MISSING ENTRY") 
                            fd.write(f'15DIFFERENT! Patient={Patient}')                       
                            fd.write('mapping {b}=>{mxo[b]} j={j} jmult={jmult}\n')
                            fd.write(f"{datatitle} xml={valuexml} expectedcomp={vmap[b][valuexml]} realcomp=MISSING ENTRY\n")                             
                else:#b not in vmap
                    logging.debug('b not in vmap')
                    valuexml=xmlelement[j][b]
                    logging.debug(f'valuexml={valuexml}')
                    zeromult=mxo[b][0]
                    jmult=zeromult.replace(multipath,newpath)

                    if valuexml==None or pat.fullmatch(valuexml) != None:
                        if jmult in composition:
                            valuecomp=composition[jmult]
                            logging.debug(f'valuexml={valuexml} valuecomp={valuecomp}')
                            if valuecomp=='None':
                                nalan+=1                       
                                logging.debug(f'mapping {b}=>{mxo[b]}')
                                logging.debug(f"{datatitle} xml={valuexml} realcomp={valuecomp}")
                                continue
                            else:
                                nalan+=1
                                ndifff+=1
                                logging.debug(f'16DIFFERENT! Patient={Patient}')
                                logging.debug(f'mapping {b}=>{mxo[b]}')
                                logging.debug(f'{datatitle} {valuexml}=>{valuecomp}')  
                                logging.debug(f'empty valuexml ')
                                fd.write(f'16DIFFERENT! Patient={Patient}')
                                fd.write(f'mapping {b}=>{mxo[b]}')
                                fd.write(f'{datatitle} {valuexml}=>{valuecomp}')  
                                fd.write(f'empty valuexml ')
                                continue  
                        else:
                            nalan+=1
                            logging.debug(f'mapping {b}=>{mxo[b]}')
                            logging.debug(f'{datatitle} {valuexml}=>nothing')  
                            logging.debug(f'empty valuexml mapped to NO element')
                            continue             

                    if len(mxo[b])==1:
                        zeromult=mxo[b][0]
                        jmult=zeromult.replace(multipath,newpath)
                        if jmult in composition:
                            valuecomp=composition[jmult]
                            logging.debug(f'valuecomp={valuecomp}')
                            v1=valuexml
                            v2=valuecomp
                            if v1 == v2:
                                nalan+=1
                                logging.debug(f'mapping {b}=>{mxo[b]} j={j} jmult={jmult}')
                                logging.debug(f"{datatitle} xml={valuexml} realcomp={valuecomp}")            
                            else:
                                if jmult.endswith('year_of_sample_collection'):
                                    l1=len(valuexml)
                                    valuecomp2=valuecomp[:l1]
                                    if valuexml==valuecomp2:
                                        nalan+=1
                                        logging.debug(f'mapping {b}=>{mxo[b]} j={j} jmult={jmult}')
                                        logging.debug(f"{datatitle} xml={valuexml} comp2={valuecomp2} realcomp={valuecomp}")
                                    else:
                                        nalan+=1
                                        ndifff+=1
                                        logging.debug(f'17DIFFERENT! Patient={Patient}')
                                        logging.debug(f'mapping {b}=>{mxo[b]} j={j} jmult={jmult}')
                                        logging.debug(f'{datatitle} xml={valuexml}=>comp2={valuecomp2} comp={valuecomp}')    
                                        fd.write(f'17DIFFERENT! Patient={Patient}')                     
                                        fd.write(f'mapping {b}=>{mxo[b]} j={j} jmult={jmult}\n')
                                        fd.write(f"xml={valuexml} comp2={valuecomp2} realcomp={valuecomp}\n")
                                elif jmult.endswith('overall_survival_status') or \
                                     jmult.endswith('surgery_start_relative') or \
                                     jmult.endswith('date_of_end_of_pharmacotherapy') or \
                                     jmult.endswith('date_of_start_of_pharmacotherapy') or \
                                     jmult.endswith('time_of_therapy_response') or \
                                     jmult.endswith('date_of_start_of_targeted_therapy') or \
                                     jmult.endswith('date_of_end_of_targeted_therapy') or \
                                     jmult.endswith('date_of_start_of_radiation_therapy') or \
                                     jmult.endswith('date_of_end_of_radiation_therapy') or \
                                     jmult.endswith('time_of_recurrence'):
                                    if notload:
                                        valuexml2='P'+str(valuexml)+'W'
                                    else: 
                                        v1=int(valuexml)*7
                                        valuexml2='P'+str(v1)+'D'
                                    if valuexml2==valuecomp:
                                        nalan+=1
                                        logging.debug(f'mapping {b}=>{jmult}')
                                        logging.debug(f"{datatitle} xml={valuexml} xml2={valuexml2} realcomp={valuecomp}")
                                    else:
                                        nalan+=1
                                        ndifff+=1
                                        logging.debug(f'18DIFFERENT! Patient={Patient}')
                                        logging.debug(f'mapping {b}=>{jmult} j={j} jmult={jmult}')
                                        logging.debug(f'{datatitle} xml={valuexml} xml2={valuexml2}=>{valuecomp}') 
                                        fd.write(f'18DIFFERENT! Patient={Patient}')                        
                                        fd.write(f'mapping {b}=>{jmult}\n')
                                        fd.write(f"xml={valuexml}  xml2={valuexml2} realcomp={valuecomp}\n")  
                                else:
                                    nalan+=1
                                    ndifff+=1
                                    logging.debug(f'19DIFFERENT! Patient={Patient}')
                                    logging.debug(f'mapping {b}=>{mxo[b]} j={j} jmult={jmult}')
                                    logging.debug(f"{datatitle} xml={valuexml} realcomp={valuecomp}")   
                                    fd.write(f'19DIFFERENT! Patient={Patient}')                     
                                    fd.write('mapping {b}=>{mxo[b]} j={j} jmult={jmult}\n')
                                    fd.write(f"{datatitle} xml={valuexml} realcomp={valuecomp}\n")
                        else:
                            nalan+=1
                            ndifff+=1
                            logging.debug(f'20DIFFERENT! Patient={Patient}')
                            logging.debug(f'mapping {b}=>{mxo[b]} j={j} jmult={jmult}')
                            logging.debug(f"{datatitle} xml={valuexml} realcomp=MISSING ENTRY")  
                            fd.write(f'20DIFFERENT! Patient={Patient}')                      
                            fd.write('mapping {b}=>{mxo[b]} j={j} jmult={jmult}\n')
                            fd.write(f"{datatitle} xml={valuexml} realcomp=MISSING ENTRY\n")
                    else:
                        i=0
                        if mxo[b][1].endswith('|value'):
                            i=1
                        elif mxo[b][2].endswith('|value'):
                            i=2
                        zeromult=mxo[b][i]
                        jmult=zeromult.replace(multipath,newpath)
                        if jmult in composition:
                            valuecomp=composition[jmult]                        
                            v1=valuexml
                            v2=valuecomp
                            if v1 == v2:
                                nalan+=1             
                                logging.debug(f'mapping {b}=>{mxo[b]} j={j} jmult={jmult}')
                                logging.debug(f"{datatitle} xml={valuexml} realcomp={valuecomp}")            
                            else:
                                if jmult.endswith('year_of_sample_collection'):
                                    l1=len(valuexml)
                                    valuecomp2=valuecomp[:l1]
                                    if valuexml != valuecomp2:
                                        nalan+=1
                                        ndifff+=1
                                        logging.debug(f'21alphaDIFFERENT! Patient={Patient}')
                                        logging.debug(f'mapping {b}=>{mxo[b]} j={j} jmult={jmult}')
                                        logging.debug(f"{datatitle} xml={valuexml} valuecomp2={valuecomp2} realcomp={valuecomp}") 
                                        fd.write(f'21alphaDIFFERENT! Patient={Patient}')                       
                                        fd.write('mapping {b}=>{mxo[b]} j={j} jmult={jmult}\n')
                                        fd.write(f"{datatitle} xml={valuexml} valuecomp2={valuecomp2} realcomp={valuecomp}\n")                                        
                                else:
                                    nalan+=1
                                    ndifff+=1
                                    logging.debug(f'21DIFFERENT! Patient={Patient}')
                                    logging.debug(f'mapping {b}=>{mxo[b]} j={j} jmult={jmult}')
                                    logging.debug(f"{datatitle} xml={valuexml} realcomp={valuecomp}") 
                                    fd.write(f'21DIFFERENT! Patient={Patient}')                       
                                    fd.write('mapping {b}=>{mxo[b]} j={j} jmult={jmult}\n')
                                    fd.write(f"{datatitle} xml={valuexml} realcomp={valuecomp}\n")       
                        else:
                            nalan+=1
                            ndifff+=1
                            logging.debug(f'22DIFFERENT! Patient={Patient}')
                            logging.debug(f'mapping {b}=>{mxo[b]} j={j} jmult={jmult}')
                            logging.debug(f"{datatitle} xml={valuexml} realcomp=MISSING ENTRY") 
                            fd.write(f'22DIFFERENT! Patient={Patient}')                       
                            fd.write('mapping {b}=>{mxo[b]} j={j} jmult={jmult}\n')
                            fd.write(f"{datatitle} xml={valuexml} realcomp=MISSING ENTRY\n")                                                   
    return ndifff,nalan               

def main():
    global dictact,dictactfile
    parser = argparse.ArgumentParser()
    parser.add_argument('--loglevel',help='the logging level:DEBUG,INFO,WARNING,ERROR or CRITICAL',default='DEBUG')
    parser.add_argument('--inputdir',help='dir containing the xmls',default='/usr/local/data/WORK/OPENEHR/ECOSYSTEM/TO_AND_FROM_CONVERTER/CODE/FROM_DB_CSV_TO_XML_CONVERTER')
    parser.add_argument('--basename',help='basename to filter xml',default='patientsFromDb_')
    parser.add_argument('--templatename',help='template id used in compositions',default=templatenamedefault)
    parser.add_argument('--fileindex',help='consider only the file with that index',default='-1')
    parser.add_argument('--notload',action='store_true',help='Run against the compositions not loaded yet')
    parser.add_argument('--dircomp',help='dir containing the compositions',default='/usr/local/data/WORK/OPENEHR/ECOSYSTEM/TO_AND_FROM_CONVERTER/CODE/RESULTS/')
    parser.add_argument('--basename_comp',help='basename for dir containing the compositions',default='myoutput')
    args=parser.parse_args()

    #input
    loglevel=getattr(logging, args.loglevel.upper(),logging.WARNING)
    if not isinstance(loglevel, int):
            raise ValueError('Invalid log level: %s' % loglevel)
    logging.basicConfig(filename='./Check.log',filemode='w',level=loglevel)

    templatename=args.templatename
    templatenamecomp=templatename.lower()
    #remap to the chosen template_id
    if templatenamecomp != 'crc_cohort7':
        for key, value in mxo.items():
            newvalue=[]
            for v in value:
                base=v.split('crc_cohort7',1)[1]
                newvalue.append(templatenamecomp+base)
            mxo[key]=newvalue
        for key, value in multi.items():
            base=value.split('crc_cohort7',1)[1]
            newvalue=templatenamecomp+base
            multi[key]=newvalue

    notload=False
    if args.notload:
        notload=True
        dircomp=args.dircomp
        print (f'notload is set to true. Compositions are loaded from {dircomp}')
        logging.info(f'notload is set to true. Compositions are loaded from {dircomp}')
        basename_comp=args.basename_comp

    inputdir=args.inputdir
    print(f'inputdir given: {inputdir}')
    logging.info(f'inputdir given: {inputdir}')

    if not os.path.exists(inputdir):
        print(f'directory {inputdir} does not exist')
        logging.error(f'directory {inputdir} does not exist')
        sys.exit(1)

    fileindex=int(args.fileindex)

    basename=args.basename

    logging.info(f'basename given: {basename}')
    print(f'basename given: {basename}')
    #get the list of files
    filelist=[]
    for filex in os.listdir(inputdir):
        if filex.startswith(basename) and filex.endswith(".xml"):
            logging.debug(f'file added {os.path.join(inputdir, filex)}')
            filelist.append(filex)
    #Now sort the list
    filelist.sort(key=lambda a: int(a.split('_')[1].split('.xml')[0]))
    for i,f in enumerate(filelist):
        logging.info(f'file {i+1} = {f}')

    filelistfullpath=[inputdir+'/'+f for f in filelist]

    # #mapping xml tag -> openEHR path read in mxo in include
    # mapping terminology values read in vmap in include

    if notload:
        dictactfile=get_compids_file(dircomp,basename_comp)
        logging.info(f'basename_comp given: {basename_comp}')
        print(f'basename_comp given: {basename_comp}')
    else:
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
                f.write('dictact={')
                nkeys=len(dictact.keys())
                for m,k in enumerate(dictact.keys()):
                    if m==nkeys-1:
                        f.write('"'+k+'" : ["'+dictact[k][0]+'" , "'+dictact[k][1]+'" ]}')
                    else:
                        f.write('"'+k+'" : ["'+dictact[k][0]+'" , "'+dictact[k][1]+'" ],')
        # logging.info('------dictact-------')
        # logging.info(dictact)

    #output file
    #file with differences
    fd=open('XMLopenEHRcompsdiff','w')
    npat=0
    #cycle over the xml files
    k=0
    totalnumberdifferences=0
    totalan=0
    npataffected=0
    totpatients=0
    for filex in filelistfullpath:
        logging.info('---------------------')
        logging.info(f'Processing {filex}')
        print('---------------------')
        print(f'Processing {filex}')
        xmlpatients=read_xml(filex)
        ns=find_ns(xmlpatients[0])


        k=k+1
        if k<fileindex:
            continue
        # if k<4:
        #      continue

        j=0
        totpatientsperfile=0
        npataffectedperfile=0
        totalnumberdifferencesperfile=0
        totalanperfile=0
        for xmlpatient in xmlpatients:
            totpatients+=1
            totpatientsperfile+=1
            nperpat=0
            j=j+1
            npat=npat+1
            if not npat%100:
                logging.info(f'{npat} patients processed')
                print(f'{npat} patients processed')
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
                        if tag=='Dataelement_68_2':
                            histo[tag]=elem[0].text
                        else:
                            histo[tag]=text
                        if i==datalen:
                            hi=False
                            Histopathology.append(histo)                    
                    elif tag=='Event':
                        hi=False
                        eventparse=True
                        if len(histo)>1:
                            Histopathology.append(histo)
                    elif i==datalen:
                        hi=False
                        if len(histo)>1:
                            Histopathology.append(histo)
                        #logging.debug(f'histo={histo} Histo={Histopathology}')
                elif sa:#sample event
                    if tag.startswith('Dataelement'):
                        sample[tag]=text
                        if i==datalen:
                            sa=False
                            Sample.append(sample)                          
                    elif tag=='Event':
                        sa=False
                        eventparse=True
                        if len(sample)>1:
                            Sample.append(sample)
                    elif i==datalen:
                        sa=False
                        if len(sample)>1:
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
                        if len(surgery)>1:
                            Surgery.append(surgery)
                    elif i==datalen:
                        su=False
                        if len(surgery)>1:
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
                        if len(pharma)>1:
                            Pharmacotherapy.append(pharma)
                    elif i==datalen:
                        ph=False
                        if len(pharma)>1:
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
                        if len(rethe)>1:
                            Responsetotherapy.append(rethe)
                    elif i==datalen:
                        re=False
                        if len(rethe)>1:
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
                        if len(tathe)>1:
                            TargetedTherapy.append(tathe)
                    elif i==datalen:
                        ta=False
                        if len(tathe)>1:
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
                        if len(radthe)>1:
                            Radiationtherapy.append(radthe)
                    elif i==datalen:
                        ra=False
                        if len(radthe)>1:
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
                    elif tag=='Location':
                        location=attr['name']

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
            
            logging.debug(f'Location={location}')
            logging.debug(f'BasicData={BasicData}')
            logging.debug(f'Histopathology={Histopathology}')
            logging.debug(f'Surgery={Surgery}')
            logging.debug(f'Sample={Sample}')
            logging.debug(f'Pharmacotherapy={Pharmacotherapy}')
            logging.debug(f'Responsetotherapy={Responsetotherapy}')
            logging.debug(f'TargetedTherapy={TargetedTherapy}')            
            logging.debug(f'Radiationtherapy={Radiationtherapy}') 

            #get composition
            if notload:
                fd.write(f'+++++++++Patient={patient}+++++++++\n')
                fd.write(f'XMLfile={filex}\n')
                filecomp=dictactfile[patient]
                fd.write(f'filecomp={filecomp}\n')
                composition=get_composition_file(filecomp)
            else:
                ehrid=dictact[patient][0]
                cid=dictact[patient][1]
                fd.write(f'+++++++++Patient={patient}+++++++++\n')
                fd.write(f'XMLfile={filex}\n')
                fd.write(f'ehrid={ehrid}  cid={cid}\n')
                composition=get_composition(client,auth,ehrid,cid,templatename)
 

            logging.debug('composition read')
            logging.debug(json.dumps(composition, indent=2))

            if 'status' in composition:
                logging.info(f'error retrieving composition for patient={patient}')
                sys.exit(1)
            #logging.debug('COMPOSITION')
            #logging.debug(composition)

            # logging.debug(f'type(composition)={type(composition)}')
            # logging.debug(f'type(mxo)={type(mxo)}')
            
            #COMPARISON
            
            #Location
            if templatenamecomp+'/context/biobank/biobank_name' in composition:
                locationfromcomp=composition[templatenamecomp+'/context/biobank/biobank_name']
                if location != locationfromcomp:
                    logging.debug(f'LOCATION DIFFERENT xml={location} comp={locationfromcomp}')
                    totalnumberdifferences+=1
                    totalnumberdifferencesperfile+=1
                    totalan+=1
                    totalanperfile+=1
            else:
                logging.debug(f'LOCATION DIFFERENT: MISSING in composition xml={location}')
                totalnumberdifferences+=1
                totalnumberdifferencesperfile+=1
                totalan+=1
                totalanperfile+=1                   

            #BasicData
            ndiffhere,nana=comparexml2comp('BasicData',BasicData,composition,fd,patient,notload)
            nperpat+=ndiffhere
            totalnumberdifferences+=ndiffhere
            totalnumberdifferencesperfile+=ndiffhere
            totalan+=nana
            totalanperfile+=nana
            logging.info(f'NDIFF Block BasicData={ndiffhere}  ndifftot={totalnumberdifferences}')
            #fd.write(f'NDIFF Block BasicData={ndiffhere}\n')
            
            #Histopathology
            ndiffhere,nana=comparexml2comp('Histopathology',Histopathology,composition,fd,patient,notload)
            nperpat+=ndiffhere
            totalnumberdifferences+=ndiffhere
            totalnumberdifferencesperfile+=ndiffhere
            totalan+=nana
            totalanperfile+=nana
            logging.info(f'NDIFF Block Histopathology={ndiffhere}  ndifftot={totalnumberdifferences}')
            #fd.write(f'NDIFF Block Histopathology={ndiffhere}\n')

            #Sample
            ndiffhere,nana=comparexml2comp('Sample',Sample,composition,fd,patient,notload)
            nperpat+=ndiffhere
            totalnumberdifferences+=ndiffhere
            totalnumberdifferencesperfile+=ndiffhere
            totalan+=nana
            totalanperfile+=nana
            logging.info(f'NDIFF Block Sample={ndiffhere}  ndifftot={totalnumberdifferences}')
            #fd.write(f'NDIFF Block Sample={ndiffhere}\n')

            #Surgery
            ndiffhere,nana=comparexml2comp('Surgery',Surgery,composition,fd,patient,notload)
            nperpat+=ndiffhere
            totalnumberdifferences+=ndiffhere
            totalnumberdifferencesperfile+=ndiffhere
            totalan+=nana
            totalanperfile+=nana
            logging.info(f'NDIFF Block Surgery={ndiffhere}  ndifftot={totalnumberdifferences}')
            #fd.write(f'NDIFF Block Surgery={ndiffhere}\n')

            #Pharmacotherapy
            ndiffhere,nana=comparexml2comp('Pharmacotherapy',Pharmacotherapy,composition,fd,patient,notload)
            nperpat+=ndiffhere
            totalnumberdifferences+=ndiffhere
            totalnumberdifferencesperfile+=ndiffhere
            totalan+=nana
            totalanperfile+=nana
            logging.info(f'NDIFF Block Pharmacotherapy={ndiffhere}  ndifftot={totalnumberdifferences}')
            #fd.write(f'NDIFF Block Pharmacotherapy={ndiffhere}\n')

            #Responsetotherapy
            ndiffhere,nana=comparexml2comp('Responsetotherapy',Responsetotherapy,composition,fd,patient,notload)
            nperpat+=ndiffhere
            totalnumberdifferences+=ndiffhere
            totalnumberdifferencesperfile+=ndiffhere
            totalan+=nana
            totalanperfile+=nana
            logging.info(f'NDIFF Block Responsetotherapy={ndiffhere}  ndifftot={totalnumberdifferences}')
            #fd.write(f'NDIFF Block Responsetotherapy={ndiffhere}\n')

            #TargetedTherapy
            ndiffhere,nana=comparexml2comp('TargetedTherapy',TargetedTherapy,composition,fd,patient,notload)
            nperpat+=ndiffhere
            totalnumberdifferences+=ndiffhere
            totalnumberdifferencesperfile+=ndiffhere
            totalan+=nana
            totalanperfile+=nana
            logging.info(f'NDIFF Block TargetedTherapy={ndiffhere}  ndifftot={totalnumberdifferences}')
            #fd.write(f'NDIFF Block TargetedTherapy={ndiffhere}\n')

            #Radiationtherapy
            ndiffhere,nana=comparexml2comp('Radiationtherapy',Radiationtherapy,composition,fd,patient,notload)
            nperpat+=ndiffhere
            totalnumberdifferences+=ndiffhere
            totalnumberdifferencesperfile+=ndiffhere
            totalan+=nana
            totalanperfile+=nana
            logging.info(f'NDIFF Block Radiationtherapy={ndiffhere}  ndifftot={totalnumberdifferences}')
            #fd.write(f'NDIFF Block Radiationtherapy={ndiffhere}\n')

            logging.debug(f'patient={patient} nerrors={nperpat}')
            if nperpat > 0:
                npataffected+=1
                npataffectedperfile+=1

        print(f'totalnumberdifferencesperfile/analysed={totalnumberdifferencesperfile}/{totalanperfile}')
        print(f'patientsaffectedbyerrorsperfile/totalpatientsperfile={npataffectedperfile}/{totpatientsperfile}')
        logging.info(f'totalnumberdifferencesperfile/analysed={totalnumberdifferencesperfile}/{totalanperfile}')
        logging.info(f'patientsaffectedbyerrorsperfile/totalpatientsperfile={npataffectedperfile}/{totpatientsperfile}')
        fd.write(f'totalnumberdifferencesperfile/analysed={totalnumberdifferencesperfile}/{totalanperfile}\n')
        fd.write(f'patientsaffectedbyerrorsperfile/totalpatientsperfile={npataffectedperfile}/{totpatientsperfile}\n')


            #if j==100: #FOR DEBUGGING. ONLY FIRST PATIENT
            #    break
        # if k==4:#FOR DEBUGGING. ONLY FIRST FILE
        #     break   
        if k==fileindex:#FOR DEBUGGING. ONLY FIRST FILE
            break  
    print(f'totalnumberdifferences/analysed={totalnumberdifferences}/{totalan}')
    print(f'patientsaffectedbyerrors/totalpatients={npataffected}/{totpatients}')
    logging.info(f'totalnumberdifferences/analysed={totalnumberdifferences}/{totalan}')
    logging.info(f'patientsaffectedbyerrors/totalpatients={npataffected}/{totpatients}')
    fd.write(f'totalnumberdifferences/analised={totalnumberdifferences}/{totalan}\n')
    fd.write(f'patientsaffectedbyerrors/totalpatients={npataffected}/{totpatients}\n')


if __name__ == '__main__':
    main()




