using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace IRSData
{
    public class FormType990EZ
    {
        private List<string> mDescriptionProgramSrvcAccomTxt;
        private List<string> mProgramServiceExpensesAmt;
        private List<string> mPersonNm;
        private List<string> mTitleTxt;

        [XPathAttibute(@"/Return/ReturnHeader/Filer/BusinessName/")]
        public string BusinessNameLine1Txt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990EZ/")]
        public string WebsiteAddressTxt { get; set; }

        [XPathAttibute(@"/Return/ReturnHeader/Filer/USAddress/")]
        public string ZIPCd { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990EZ/ProgramSrvcAccomplishmentGrp/", true)]
        public string DescriptionProgramSrvcAccomTxt
        {

            get
            {
                return AggregateRepeaters(mDescriptionProgramSrvcAccomTxt);
            }
            set
            {
                mDescriptionProgramSrvcAccomTxt = SetRepeaterValue(mDescriptionProgramSrvcAccomTxt, value);
            }
        }


        [XPathAttibute(@"/Return/ReturnData/IRS990EZ/")]
        public string ContributionsGiftsGrantsEtcAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990EZ/ProgramSrvcAccomplishmentGrp/", true)]
        public string ProgramServiceExpensesAmt
        {
            get
            {
                return AggregateRepeaters(mProgramServiceExpensesAmt);
            }
            set
            {
                mProgramServiceExpensesAmt = SetRepeaterValue(mProgramServiceExpensesAmt, value);
            }
        }
    

        [XPathAttibute(@"/Return/ReturnData/IRS990EZ/")]
        public string TotalRevenueAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990EZ/")]
        public string TotalExpensesAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990EZ/")]
        public string ExcessOrDeficitForYearAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990EZ/")]
        public string NetAssetsOrFundBalancesBOYAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990EZ/")]
        public string NetAssetsOrFundBalancesEOYAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990EZ/")]
        public string MembershipDuesAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990EZ/")]
        public string FeesAndOtherPymtToIndCntrctAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990EZ/")]
        public string PoliticalCampaignActyInd { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990EZ/")]
        public string LobbyingActivitiesInd { get; set; }

        //[XPathAttibute(@"/Return/ReturnData/IRS990EZ/")]
        //public string SalariesOtherCompEmplBnftAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990EZ/OfficerDirectorTrusteeEmplGrp/", true)]
        public string PersonNm
        {
            get
            {
                return AggregateRepeaters(mPersonNm);
            }
            set
            {
                mPersonNm = SetRepeaterValue(mPersonNm, value);
            }
        }

        [XPathAttibute(@"/Return/ReturnData/IRS990EZ/OfficerDirectorTrusteeEmplGrp/", true)]
        public string TitleTxt
        {
            get
            {
                return AggregateRepeaters(mTitleTxt);
            }
            set
            {
                mTitleTxt = SetRepeaterValue(mTitleTxt, value);
            }
        }

        internal string AggregateRepeaters(List<string> aggRep, string seperater = ";")
        {
            string rtn = string.Empty;
            if (aggRep != null)
            {
                rtn = aggRep.Aggregate((a, b) => a + seperater + " " + b);
            }

            return rtn;
        }

        internal List<string> SetRepeaterValue(List<string> rep, string value)
        {
            if (rep == null)
            {
                rep = new List<string>();
            }

            rep.Add(value);

            return rep;
        }

    }
}
